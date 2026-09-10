"""ODsay 응답 파싱(_build_legs)이 실제로 겪는 응답 변형을 견디는지 확인한다.

ODsay 서버 키는 공인 IP 허용 목록 기반이라 개발 환경에서 실제 호출이 막히는 일이
잦다(README "검증한 것/검증하지 못한 것" 참고). 그래서 파싱만은 실제 호출 없이
여기서 검증하고, 실제 응답 스키마 자체는 probe_odsay.py로 따로 확인한다.

실행: python test_route_parse.py   (pytest가 있으면 pytest test_route_parse.py 도 동작)
"""

import json
import tempfile
from pathlib import Path

from main import (
    _build_legs,
    _build_path,
    _bus_type,
    _friendly_odsay_error,
    _load_seat_lookup,
    _odsay_error_message,
)


def test_bus_leg_uses_pass_stops_for_path_and_keeps_ars_id():
    """버스 구간은 경유 정류장을 모두 이어 경로를 만들고, ARS 번호를 보존한다."""
    # Arrange — 실제 응답과 같이 좌표가 문자열로 오는 경우를 섞었다.
    path_obj = {
        "subPath": [
            {
                "trafficType": 2,
                "sectionTime": 12,
                "distance": 4200,
                "startName": "강남역",
                "endName": "판교역",
                # 실제 응답: 노선마다 지자체 노선 ID(busLocalBlID)와 버스 종류 코드(type)가 온다.
                "lane": [
                    {"busNo": "402", "busLocalBlID": "100100061", "type": 11},
                    {"busNo": "143", "busLocalBlID": "100100022", "type": 11},
                ],
                "passStopList": {
                    "stations": [
                        {"stationName": "강남역", "arsID": "22001", "x": "127.0276", "y": "37.4979"},
                        {"stationName": "양재역", "arsID": "22002", "x": 127.0345, "y": 37.4842},
                        {"stationName": "판교역", "arsID": "22003", "x": 127.1114, "y": 37.3947},
                    ]
                },
            }
        ]
    }

    # Act
    (leg,) = _build_legs(path_obj)

    # Assert
    assert leg["mode"] == "bus"
    assert leg["routeName"] == "143, 402"  # 정렬되어 합쳐진다
    assert leg["lanes"][0] == {"busNo": "402", "localRouteId": "100100061", "type": 11, "busType": "일반"}
    assert len(leg["path"]) == 3
    assert leg["path"][0] == {"lat": 37.4979, "lng": 127.0276}  # 문자열도 float으로
    assert [s["arsId"] for s in leg["stations"]] == ["22001", "22002", "22003"]


def _stations(*points):
    return {"stations": [{"stationName": f"s{i}", "x": x, "y": y} for i, (x, y) in enumerate(points)]}


def test_walk_legs_are_bridged_from_neighbors_and_endpoints():
    """실제 ODsay 응답의 도보 구간에는 좌표가 전혀 없다. 앞 구간의 끝점과 뒤 구간의
    첫점을 잇고, 맨 앞/뒤 도보는 요청한 출발지·목적지 좌표를 쓴다."""
    origin, dest = {"lat": 37.0, "lng": 127.0}, {"lat": 37.9, "lng": 127.9}
    path_obj = {
        "subPath": [
            {"trafficType": 3, "sectionTime": 1},  # 도보: 좌표 없음
            {"trafficType": 2, "passStopList": _stations((127.1, 37.1), (127.2, 37.2))},
            {"trafficType": 3, "sectionTime": 2},  # 도보(환승): 좌표 없음
            {"trafficType": 1, "passStopList": _stations((127.3, 37.3), (127.4, 37.4))},
            {"trafficType": 3, "sectionTime": 3},  # 도보: 좌표 없음
        ]
    }

    legs = _build_legs(path_obj, origin=origin, dest=dest)

    assert legs[0]["path"] == [origin, {"lat": 37.1, "lng": 127.1}]
    assert legs[2]["path"] == [{"lat": 37.2, "lng": 127.2}, {"lat": 37.3, "lng": 127.3}]
    assert legs[4]["path"] == [{"lat": 37.4, "lng": 127.4}, dest]
    assert legs[0]["stations"] == [] and "routeName" not in legs[0]


def test_transit_leg_without_stations_falls_back_to_start_end_coords():
    """정류장 목록이 비어 온 버스/지하철 구간은 startX/Y·endX/Y가 있으면 그 두 점을 잇는다."""
    path_obj = {
        "subPath": [
            {
                "trafficType": 2,
                "passStopList": {"stations": []},
                "startX": 127.0276, "startY": 37.4979,
                "endX": 127.0281, "endY": 37.4990,
            }
        ]
    }

    (leg,) = _build_legs(path_obj)

    assert leg["path"] == [
        {"lat": 37.4979, "lng": 127.0276},
        {"lat": 37.4990, "lng": 127.0281},
    ]


def test_subway_leg_uses_lane_name():
    """지하철 구간의 노선명은 lane[].name에서 온다 (버스는 busNo)."""
    path_obj = {
        "subPath": [
            {
                "trafficType": 1,
                "sectionTime": 20,
                "lane": [{"name": "신분당선"}],
                "passStopList": {
                    "stations": [
                        {"stationName": "강남", "x": 127.0276, "y": 37.4979},
                        {"stationName": "판교", "x": 127.1114, "y": 37.3947},
                    ]
                },
            }
        ]
    }

    (leg,) = _build_legs(path_obj)

    assert leg["mode"] == "subway"
    assert leg["routeName"] == "신분당선"
    assert len(leg["path"]) == 2


def test_missing_and_broken_fields_do_not_raise():
    """좌표 누락·빈 정류장 목록·처음 보는 trafficType 모두 예외 없이 넘어가야 한다.
    (실제로 ODsay 응답 모양을 잘못 가정해 500이 났던 이력이 있다.)"""
    path_obj = {
        "subPath": [
            {"trafficType": 3},  # 좌표가 아예 없는 도보
            {"trafficType": 2, "passStopList": {"stations": []}, "lane": []},  # 빈 목록
            {"trafficType": 99, "startX": "", "startY": None},  # 미지의 코드 + 깨진 좌표
            {"trafficType": 2, "passStopList": {"stations": [
                {"stationName": "좌표없음", "arsID": "1", "x": None, "y": None},
                {"stationName": "정상", "arsID": "2", "x": 127.0, "y": 37.5},
            ]}},
        ]
    }

    legs = _build_legs(path_obj)

    assert len(legs) == 4
    # 이웃에도 출발지·목적지에도 좌표가 없으면 빈 경로로 남는다 — 프론트엔드는 2점 미만은 그리지 않는다.
    assert legs[0]["path"] == []
    assert legs[1]["path"] == []
    assert legs[2]["mode"] == "unknown(99)"
    # 좌표 없는 정류장은 경로에서 빠지지만 stations에는 남는다(ARS 번호가 필요하므로).
    assert legs[3]["path"] == []  # 유효 좌표가 1개뿐이라 선을 그릴 수 없다
    assert len(legs[3]["stations"]) == 2
    assert legs[3]["stations"][0]["lat"] is None


def test_local_station_id_is_used_when_ars_id_missing():
    """서울 밖 정류장은 arsID 없이 localStationID만 오는 경우가 있다."""
    path_obj = {
        "subPath": [
            {
                "trafficType": 2,
                "passStopList": {"stations": [
                    {"stationName": "동탄2신도시", "localStationID": "L9", "x": 127.1, "y": 37.2},
                    {"stationName": "다음", "localStationID": "L10", "x": 127.2, "y": 37.3},
                ]},
            }
        ]
    }

    (leg,) = _build_legs(path_obj)

    assert [s["arsId"] for s in leg["stations"]] == ["L9", "L10"]


def test_bus_type_from_odsay_code():
    """ODsay 버스 종류 코드 → 일반/광역(입석금지). 실제 응답에서 3=마을, 1=일반, 4=직행좌석, 14=광역이 확인됐다."""
    assert [_bus_type(c) for c in (1, 3, 11, 12, None)] == ["일반"] * 5
    assert [_bus_type(c) for c in (4, 6, 14)] == ["광역"] * 3


def test_seat_lookup_loads_rows_and_missing_file_gives_empty_table():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "lookup.json"
        p.write_text(json.dumps([{"route": "402", "bus_type": "일반", "hour": 8, "p_capacity": 0.61}]), encoding="utf-8")
        assert _load_seat_lookup(p) == {("402", 8): 0.61}
        assert _load_seat_lookup(Path(d) / "없음.json") == {}  # 파일이 없어도 서버는 뜬다 (경고만)


def test_build_path_attaches_seat_probability_per_lane():
    """학습된 노선은 그 시각의 확률, 아닌 노선은 None(데이터 없음) — 추정치로 채우지 않는다."""
    path_obj = {
        "pathType": 3,
        "info": {"totalTime": 67, "payment": 5250, "totalWalk": 361, "busTransitCount": 1, "subwayTransitCount": 0},
        "subPath": [
            {
                "trafficType": 2,
                "lane": [{"busNo": "402", "type": 11}, {"busNo": "M4434", "type": 14}],
                "passStopList": _stations((127.0, 37.0), (127.1, 37.1)),
            }
        ],
    }

    path = _build_path(path_obj, None, None, hour=8, seat_table={("402", 8): 0.61, ("402", 9): 0.9})

    assert path["pathType"] == "mixed"
    assert (path["totalTime"], path["payment"], path["totalWalk"]) == (67, 5250, 361)
    (leg,) = path["legs"]
    assert leg["lanes"][0]["seatProbability"] == 0.61  # 8시 값
    assert leg["lanes"][1]["seatProbability"] is None  # M4434는 학습 데이터에 없음
    assert (leg["lanes"][0]["busType"], leg["lanes"][1]["busType"]) == ("일반", "광역")


def test_odsay_error_message_handles_list_dict_and_string():
    """ODsay의 error 필드는 리스트로도, 딕셔너리로도, 문자열로도 온다."""
    assert _odsay_error_message({"error": [{"code": "500", "message": "[ApiKeyAuthFailed] x"}]}) == "[ApiKeyAuthFailed] x"
    assert _odsay_error_message({"error": {"msg": "no path"}}) == "no path"
    assert _odsay_error_message({"error": "plain"}) == "plain"


def test_api_key_auth_failed_points_to_ip_allowlist_not_key():
    """인증 실패는 키가 아니라 IP 허용 목록 문제로 안내하고, 등록할 IP를 보여준다."""
    msg = _friendly_odsay_error("[ApiKeyAuthFailed] ApiKey authentication failed.", "222.107.124.161")
    assert "222.107.124.161" in msg
    assert "허용 목록" in msg
    assert "ODSAY_API_KEY" not in msg  # "키를 다시 확인하라"는 오해를 주면 안 된다

    no_ip = _friendly_odsay_error("[ApiKeyAuthFailed] ...", None)
    assert "현재 공인 IP를" in no_ip  # IP 조회에 실패해도 무엇을 등록할지는 알려준다

    other = _friendly_odsay_error("[NoResult] no route", None)
    assert other.endswith("[NoResult] no route")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("전부 통과")
