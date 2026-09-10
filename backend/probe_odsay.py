"""ODsay 실제 응답을 한 번 찍어보고, trafficType 코드 매핑이 맞는지 확인하는 도구.

main.py는 `trafficType 1=지하철, 2=버스, 3=도보`로 가정하고 있는데, 이 값은 여러
공개 자료에서 공통적으로 확인되는 것일 뿐 실제 응답으로 검증된 적이 없다
(기획서 6장 체크리스트의 미완료 항목). 이 스크립트는 lane/passStopList 같은 다른
필드로 각 구간의 정체를 독립적으로 추론해서, 그 결과가 매핑과 일치하는지 대조한다.

실행:
    python probe_odsay.py                    # 강남역 -> 판교역
    python probe_odsay.py 127.02 37.49 127.11 37.39   # 출발 경도 위도 도착 경도 위도

ODsay "서버" 플랫폼 키는 공인 IP 허용목록 기반이라, [ApiKeyAuthFailed]가 나오면
키가 틀린 게 아니라 현재 공인 IP가 ODsay 콘솔에 등록되지 않은 것이다.
"""

import json
import sys

import httpx

from main import (
    ODSAY_API_KEY,
    ODSAY_TRAFFIC_TYPE,
    _build_legs,
    _friendly_odsay_error,
    _is_placeholder,
    _odsay_error_message,
)

DEFAULT_COORDS = (127.0276, 37.4979, 127.1114, 37.3947)  # 강남역 -> 판교역


def infer_mode(sub):
    """trafficType을 보지 않고, 다른 필드만으로 구간의 정체를 추론한다."""
    lanes = sub.get("lane") or []
    if any(l.get("busNo") for l in lanes):
        return "bus"
    if any(l.get("subwayCode") or l.get("name") for l in lanes):
        return "subway"
    if not lanes:
        return "walk"
    return "?"


def main():
    if _is_placeholder(ODSAY_API_KEY):
        print("ODSAY_API_KEY가 .env에 설정되어 있지 않습니다.")
        return 1

    args = sys.argv[1:]
    sx, sy, ex, ey = map(float, args) if len(args) == 4 else DEFAULT_COORDS
    print(f"조회: ({sx}, {sy}) -> ({ex}, {ey})")

    resp = httpx.get(
        "https://api.odsay.com/v1/api/searchPubTransPathT",
        params={"SX": sx, "SY": sy, "EX": ex, "EY": ey,
                "OPT": 0, "SearchPathType": 0, "apiKey": ODSAY_API_KEY},
        timeout=15.0,
    )
    print(f"HTTP {resp.status_code}")
    data = resp.json()

    if "error" in data:
        try:
            public_ip = httpx.get("https://api.ipify.org", timeout=3.0).text.strip()
        except httpx.HTTPError:
            public_ip = None
        print(_friendly_odsay_error(_odsay_error_message(data), public_ip))
        return 1

    paths = data.get("result", {}).get("path", [])
    if not paths:
        print("경로를 찾지 못했습니다.")
        return 1

    best = paths[0]
    print(f"\n총 {best.get('info', {}).get('totalTime')}분, "
          f"{best.get('info', {}).get('payment')}원\n")

    print("=== trafficType 매핑 대조 ===")
    mismatches = 0
    for i, sub in enumerate(best.get("subPath", [])):
        code = sub.get("trafficType")
        mapped = ODSAY_TRAFFIC_TYPE.get(code, f"unknown({code})")
        inferred = infer_mode(sub)
        ok = mapped == inferred
        mismatches += 0 if ok else 1
        mark = "일치" if ok else ">>> 불일치 <<<"
        print(f"[{i}] trafficType={code} → 매핑 '{mapped}' / 추론 '{inferred}'  {mark}")
        print(f"     {sub.get('startName')} → {sub.get('endName')}, "
              f"lane={json.dumps(sub.get('lane') or [], ensure_ascii=False)[:80]}")

    print("\n=== 파싱 결과 (프론트엔드가 받는 형태) ===")
    for leg in _build_legs(best, origin={"lat": sy, "lng": sx}, dest={"lat": ey, "lng": ex}):
        print(f"  {leg['mode']:8} {str(leg['sectionTime']) + '분':>5}  "
              f"경로점 {len(leg['path'])}개, 정류장 {len(leg['stations'])}개  "
              f"{leg.get('routeName', '')}")
        if leg["stations"]:
            head = leg["stations"][0]
            print(f"           첫 정류장: {head['name']} (ARS {head['arsId']})")

    if mismatches:
        print(f"\n{mismatches}개 구간이 불일치합니다 — main.py의 ODSAY_TRAFFIC_TYPE을 고쳐야 합니다.")
        return 1
    print("\n모든 구간에서 ODSAY_TRAFFIC_TYPE 매핑이 실제 응답과 일치합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
