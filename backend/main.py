"""
"내가 과연 탈 수 있을까?" — 실제 지도/검색 연동 프로토타입 백엔드 (FastAPI)

이 서버가 하는 일:
  1) 프론트엔드(React/Vite)가 지도를 그릴 때 필요한, 공개해도 되는 설정값(JS 키)을
     내려준다 (/api/config).
  2) 브라우저 대신 카카오 로컬 API(키워드 장소 검색)를 호출해주는 프록시
     엔드포인트를 제공한다 (/api/search).
  3) ODsay 대중교통 길찾기를 대신 호출해 경로 목록(추천 + 대안)을 돌려주고, 각 버스
     노선에 ../model/congestion_lookup_real.json(오프라인 GBM 학습 결과)의 시간대별
     좌석 여유 확률을 붙여준다 (/api/route).
  4) (선택) `npm run build`로 만든 프론트엔드 정적 빌드 결과(frontend/dist)가
     있으면 그것도 그대로 서빙해서, 개발 서버 없이 이 백엔드 하나만으로 배포할
     수 있게 한다.

REST API 키를 서버에서만 들고 있는 이유: 카카오 REST API 키는 브라우저에 노출되면
안 되는 민감한 인증 정보라서(카카오 공식 문서에서도 서버 호출을 권장한다), 검색
요청을 프론트엔드가 아니라 이 서버가 대신 카카오에 보낸다. 반대로 지도를 그리는
"JavaScript 키"는 원래도 브라우저에 노출되는 것을 전제로 하는 키(대신 카카오
콘솔에 등록한 도메인에서만 동작)라서, /api/config를 통해 프론트엔드에 그대로
내려준다.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "").strip()
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()
ODSAY_API_KEY = os.getenv("ODSAY_API_KEY", "").strip()


def _is_placeholder(value: str) -> bool:
    return (not value) or ("여기에" in value)


if _is_placeholder(KAKAO_JS_KEY):
    print("[경고] KAKAO_JS_KEY가 설정되지 않았습니다. .env.example을 .env로 복사하고 실제 키를 넣어주세요.")
if _is_placeholder(KAKAO_REST_API_KEY):
    print("[경고] KAKAO_REST_API_KEY가 설정되지 않았습니다. .env.example을 .env로 복사하고 실제 키를 넣어주세요.")
if _is_placeholder(ODSAY_API_KEY):
    print("[경고] ODSAY_API_KEY가 설정되지 않았습니다. .env.example을 .env로 복사하고 실제 키를 넣어주세요.")

# ODsay 응답의 trafficType 코드. ODsay 공식 문서(코드정의 표)에서 공통적으로 쓰이는
# 값이지만, 이 환경에서는 실제 API를 호출해 응답을 직접 확인할 수 없었다 — 사용자가
# 실제 키로 처음 호출해볼 때, 아래 매핑과 실제 응답이 맞는지 한 번은 확인해보는 것을
# 권장한다 (README "검증한 것/검증하지 못한 것" 참고).
ODSAY_TRAFFIC_TYPE = {1: "subway", 2: "bus", 3: "walk"}
ODSAY_PATH_TYPE = {1: "subway", 2: "bus", 3: "mixed"}  # 경로 전체의 수단 조합

# ODsay 버스 종류 코드 중 입석이 금지되는 좌석형(광역) 버스. 기획서 2-3: 광역버스는 정원이
# 곧 좌석수라 만석이면 정류장을 무정차 통과하므로, 좌석 여유 확률의 의미가 일반버스와 다르다.
# ponytail: 4=직행좌석, 6=간선급행, 14=광역만 광역으로 본다. 노선별 예외는 데이터가 생기면 조정.
ODSAY_SEATED_BUS_TYPES = {4, 6, 14}

KST = timezone(timedelta(hours=9))  # 한국은 DST가 없어 고정 오프셋으로 충분하다 (Windows에 tzdata 없어도 동작)

# bus_congestion_pipeline.py(model/)가 내보낸 시간대별 좌석 여유 확률. 요일 정보는 원본
# 데이터(월 단위 집계)에 없어서 노선 × 시각만 있다 — 기획서 5-1 참고.
_SEAT_LOOKUP_PATH = Path(__file__).resolve().parent.parent / "model" / "congestion_lookup_real.json"


def _bus_type(code):
    return "광역" if code in ODSAY_SEATED_BUS_TYPES else "일반"


def _load_seat_lookup(path):
    """룩업 테이블을 {(노선번호, 시각): 좌석 여유 확률}로 읽는다. 파일이 없으면 빈 표 —
    경로 조회는 그대로 되고 좌석 확률만 '데이터 없음'으로 나간다."""
    if not path.exists():
        print(f"[경고] 좌석 여유 룩업 테이블이 없습니다: {path} — 좌석 확률은 '데이터 없음'으로 표시됩니다.")
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {(str(r["route"]), int(r["hour"])): float(r["p_capacity"]) for r in rows}


_SEAT_LOOKUP = _load_seat_lookup(_SEAT_LOOKUP_PATH)


def _odsay_error_message(data):
    """ODsay는 HTTP 200에도 에러를 담아 보낸다. "error"가 리스트/딕셔너리/문자열 어느
    모양으로 와도 메시지 문자열 하나로 만든다 (리스트로 와서 500이 났던 이력이 있다)."""
    err = data["error"]
    err_item = err[0] if isinstance(err, list) and err else err
    if isinstance(err_item, dict):
        return err_item.get("message") or err_item.get("msg") or str(err_item)
    return str(err_item)


async def _public_ip():
    """이 서버가 밖으로 나갈 때 쓰는 공인 IP. ODsay "서버" 키의 IP 허용 목록에 등록해야
    하는 값이 정확히 이것이다. 에러 안내에만 쓰이므로 조회에 실패하면 None."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            return (await client.get("https://api.ipify.org")).text.strip() or None
    except httpx.HTTPError:
        return None


def _friendly_odsay_error(err_msg, public_ip=None):
    """ODsay 에러를 사용자가 고칠 수 있는 말로 바꾼다.
    [ApiKeyAuthFailed]는 키가 틀려서가 아니라 대부분 "서버" 플랫폼 키의 IP 허용 목록에
    이 서버의 공인 IP가 없어서 난다 — 집/회사/핫스팟으로 회선이 바뀌면 매번 재발한다.
    실제로 두 번 겪었고, 그때마다 "키를 확인하라"는 안내가 원인을 가렸다."""
    if "ApiKeyAuthFailed" not in err_msg:
        return f"ODsay 경로 탐색에 실패했습니다: {err_msg}"
    where = f"현재 공인 IP {public_ip}" if public_ip else "이 서버의 현재 공인 IP"
    return (
        "ODsay가 이 서버의 IP를 허용 목록에서 찾지 못했습니다(ApiKeyAuthFailed). "
        f"lab.odsay.com > 내 애플리케이션 > 서버 플랫폼의 IP 목록에 {where}를 등록하세요. "
        "인터넷 회선이 바뀌면 IP도 바뀌어 다시 등록해야 합니다."
    )


def _coord(x, y):
    """ODsay의 x(경도)/y(위도)를 프론트엔드가 쓰는 {lat, lng}로 바꾼다.
    값이 없거나 숫자로 못 읽히면 None을 돌려준다 (ODsay는 좌표를 문자열로
    보내기도 하고, 도보 구간에서는 아예 빼고 보내는 경우도 있다)."""
    try:
        return {"lat": float(y), "lng": float(x)}
    except (TypeError, ValueError):
        return None


def _build_legs(path_obj, origin=None, dest=None):
    """ODsay 경로 하나(path)를 프론트엔드가 그대로 쓸 수 있는 구간(leg) 목록으로 바꾼다.

    각 leg에 담기는 것:
      - path: 지도에 선으로 그릴 좌표 목록. 버스/지하철은 경유 정류장을 모두 잇는다.
        도보 구간은 ODsay가 좌표를 아예 주지 않으므로(실제 응답으로 확인) 앞 구간의
        마지막 점과 뒤 구간의 첫 점을 이어 만들고, 맨 앞/뒤 도보는 요청한 출발지
        (origin)·목적지(dest) 좌표를 쓴다.
      - stations: 정류장 이름 + ARS 번호. 실시간 버스도착정보 API가 ARS 번호로
        정류장을 지목하기 때문에, "이 정류장에서 이 버스를 탈 확률"을 계산할 때
        승차 정류장을 특정하는 데 쓴다.
      - lanes(버스만): 노선번호 + 지자체 노선 ID(busLocalBlID) + ODsay 버스 종류 코드(type).
        도착정보 API가 노선을 이 ID로 지목하고, 종류 코드는 일반/광역(입석금지) 구분에 쓴다.

    ODsay 응답은 필드가 빠지거나 리스트/문자열로 모양이 바뀌는 경우가 있어서
    (실제로 error 필드가 리스트로 와서 500이 났던 이력이 있다) 전부 방어적으로 읽는다.
    """
    legs = []
    for sub in path_obj.get("subPath", []):
        traffic_code = sub.get("trafficType")
        mode = ODSAY_TRAFFIC_TYPE.get(traffic_code, f"unknown({traffic_code})")

        stations = []
        for st in (sub.get("passStopList") or {}).get("stations") or []:
            pos = _coord(st.get("x"), st.get("y"))
            stations.append(
                {
                    "name": st.get("stationName"),
                    # 서울 정류장은 arsID로 오고, 그 밖 지역은 localStationID만 오는
                    # 경우가 있어 둘 중 있는 값을 쓴다.
                    "arsId": st.get("arsID") or st.get("localStationID"),
                    "lat": pos["lat"] if pos else None,
                    "lng": pos["lng"] if pos else None,
                }
            )

        # ponytail: 정류장을 직선으로 이은 근사 경로다. 실제 도로 형상이 필요하면
        # ODsay loadLane API를 info.mapObj로 한 번 더 호출해야 한다.
        coords = [{"lat": s["lat"], "lng": s["lng"]} for s in stations if s["lat"] is not None]
        if len(coords) < 2:
            ends = [
                _coord(sub.get("startX"), sub.get("startY")),
                _coord(sub.get("endX"), sub.get("endY")),
            ]
            coords = [c for c in ends if c]

        leg = {
            "mode": mode,
            "sectionTime": sub.get("sectionTime"),  # 분
            "distance": sub.get("distance"),  # 미터
            "startName": sub.get("startName"),
            "endName": sub.get("endName"),
            "path": coords,
            "stations": stations,
        }

        lanes = sub.get("lane") or []
        if mode == "bus" and lanes:
            leg["routeName"] = ", ".join(sorted({str(l.get("busNo", "")) for l in lanes if l.get("busNo")}))
            leg["lanes"] = [
                {
                    "busNo": l.get("busNo"),
                    "localRouteId": l.get("busLocalBlID"),
                    "type": l.get("type"),
                    "busType": _bus_type(l.get("type")),
                }
                for l in lanes
            ]
        elif mode == "subway" and lanes:
            leg["routeName"] = ", ".join(sorted({str(l.get("name", "")) for l in lanes if l.get("name")}))
        legs.append(leg)

    # 좌표가 없는 구간(도보)을 이웃 구간의 끝점/첫점으로 잇는다.
    for i, leg in enumerate(legs):
        if leg["path"]:
            continue
        start = _nearest_path_point(legs, i, -1) or origin
        end = _nearest_path_point(legs, i, +1) or dest
        leg["path"] = [p for p in (start, end) if p]
    return legs


def _build_path(path_obj, origin, dest, hour, seat_table):
    """ODsay 경로 하나를 요약(소요시간·요금·환승) + 구간 목록으로 만들고, 버스 노선마다
    그 시각의 좌석 여유 확률을 붙인다. 학습된 노선(지금은 402·143)이 아니면 None —
    프론트엔드는 '데이터 없음'으로 표시한다. 없는 값을 추정치로 채우지는 않는다(기획서 3-3)."""
    info = path_obj.get("info", {})
    legs = _build_legs(path_obj, origin, dest)
    for leg in legs:
        for lane in leg.get("lanes", []):
            lane["seatProbability"] = seat_table.get((str(lane["busNo"]), hour))
    return {
        "pathType": ODSAY_PATH_TYPE.get(path_obj.get("pathType"), "mixed"),
        "totalTime": info.get("totalTime"),  # 분
        "payment": info.get("payment"),  # 원
        "totalDistance": info.get("totalDistance"),  # 미터
        "totalWalk": info.get("totalWalk"),  # 미터
        "busTransitCount": info.get("busTransitCount"),
        "subwayTransitCount": info.get("subwayTransitCount"),
        "legs": legs,
    }


def _nearest_path_point(legs, i, step):
    """i번째 구간에서 step 방향(-1 앞 / +1 뒤)으로 가장 가까운, 좌표가 있는 구간의
    끝점(앞쪽) 또는 첫점(뒤쪽). 없으면 None."""
    j = i + step
    while 0 <= j < len(legs):
        if legs[j]["path"]:
            return legs[j]["path"][-1] if step < 0 else legs[j]["path"][0]
        j += step
    return None

app = FastAPI(title="내가 과연 탈 수 있을까 — 실제 지도 연동 API")

# 개발 중에는 Vite 프록시(vite.config.js의 server.proxy)를 거치므로 CORS가 필요 없지만,
# 프론트엔드를 다른 포트/도메인에서 별도로 띄워 직접 호출하는 경우를 대비해 열어둔다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/config")
def get_config():
    """프론트엔드가 지도를 그릴 때 필요한 (공개해도 되는) 설정값만 내려준다."""
    return {"kakaoJsKey": KAKAO_JS_KEY}


@app.get("/api/search")
async def search_places(query: str = Query("", description="검색할 장소명/건물명")):
    """장소명/건물명으로 검색 → 검색창 자동완성 드롭다운에 사용.
    카카오 로컬 "키워드로 장소 검색" API를 그대로 감싼 프록시."""
    query = query.strip()
    if not query:
        return {"results": []}

    if _is_placeholder(KAKAO_REST_API_KEY):
        raise HTTPException(
            status_code=500,
            detail="KAKAO_REST_API_KEY가 서버(backend/.env)에 설정되어 있지 않습니다.",
        )

    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": query, "size": 8}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers=headers,
                params=params,
            )
    except httpx.HTTPError as exc: 
        raise HTTPException(status_code=500, detail=f"카카오 API 호출 중 오류가 발생했습니다: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"카카오 API 호출에 실패했습니다: {resp.text}",
        )

    data = resp.json()
    results = [
        {
            "name": doc.get("place_name", ""),
            "address": doc.get("road_address_name") or doc.get("address_name") or "",
            # 카카오 로컬 API 응답 기본 좌표계는 WGS84: x=경도(longitude), y=위도(latitude)
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
        }
        for doc in data.get("documents", [])
    ]
    return {"results": results}


@app.get("/api/route")
async def search_route(
    sx: float = Query(..., description="출발지 경도"),
    sy: float = Query(..., description="출발지 위도"),
    ex: float = Query(..., description="도착지 경도"),
    ey: float = Query(..., description="도착지 위도"),
):
    """두 좌표 사이의 실제 대중교통(도보+버스+지하철) 경로 목록을 ODsay API로 조회한다.
    ODsay는 한 번에 여러 경로(지하철/버스/혼합, 보통 10개 안팎)를 추천 순으로 돌려준다.
    첫 번째가 추천 경로, 나머지는 대안(기획서 4장) — 전부 내려주고 프론트엔드가 골라 보여준다.
    버스 구간의 노선마다 지금 시각의 좌석 여유 확률(오프라인 GBM 룩업)을 함께 붙인다."""

    if _is_placeholder(ODSAY_API_KEY):
        raise HTTPException(
            status_code=500,
            detail="ODSAY_API_KEY가 서버(backend/.env)에 설정되어 있지 않습니다.",
        )

    params = {
        "SX": sx,
        "SY": sy,
        "EX": ex,
        "EY": ey,
        "OPT": 0,  # 0 = 추천경로 순 정렬
        "SearchPathType": 0,  # 0 = 지하철/버스 모두 포함
        "apiKey": ODSAY_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.odsay.com/v1/api/searchPubTransPathT",
                params=params,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail=f"ODsay API 호출 중 오류가 발생했습니다: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"ODsay API 호출에 실패했습니다: {resp.text}",
        )

    data = resp.json()

    # ODsay는 HTTP 200이어도 좌표 근처에 정류장이 없거나 IP/키 인증에 실패한 경우
    # 에러를 200에 담아 보낸다. IP 허용 목록 문제면 등록해야 할 공인 IP까지 같이 알려준다.
    if "error" in data:
        err_msg = _odsay_error_message(data)
        public_ip = await _public_ip() if "ApiKeyAuthFailed" in err_msg else None
        raise HTTPException(status_code=502, detail=_friendly_odsay_error(err_msg, public_ip))

    paths = data.get("result", {}).get("path", [])
    if not paths:
        return {"found": False, "paths": []}

    origin, dest = {"lat": sy, "lng": sx}, {"lat": ey, "lng": ex}
    hour = datetime.now(KST).hour  # ponytail: "지금 출발" 기준. 출발 시각 선택 UI가 붙으면 쿼리로 받는다.
    return {
        "found": True,
        # OPT=0(추천경로) 순서 그대로 — 첫 번째가 추천 경로, 나머지는 대안.
        "paths": [_build_path(p, origin, dest, hour, _SEAT_LOOKUP) for p in paths],
    }


# 프로덕션 배포용: 프론트엔드 빌드 결과(frontend/dist)가 있으면 그대로 서빙한다.
# API 라우트를 먼저 등록했기 때문에 /api/* 요청은 항상 위 핸들러가 먼저 처리하고,
# 그 외 경로만 이 정적 파일 마운트로 넘어간다.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
