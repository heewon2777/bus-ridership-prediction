"""
"내가 과연 탈 수 있을까?" — 실제 지도/검색 연동 프로토타입 백엔드 (FastAPI)

이 서버가 하는 일은 딱 세 가지다:
  1) 프론트엔드(React/Vite)가 지도를 그릴 때 필요한, 공개해도 되는 설정값(JS 키)을
     내려준다 (/api/config).
  2) 브라우저 대신 카카오 로컬 API(키워드 장소 검색)를 호출해주는 프록시
     엔드포인트를 제공한다 (/api/search).
  3) (선택) `npm run build`로 만든 프론트엔드 정적 빌드 결과(frontend/dist)가
     있으면 그것도 그대로 서빙해서, 개발 서버 없이 이 백엔드 하나만으로 배포할
     수 있게 한다.

REST API 키를 서버에서만 들고 있는 이유: 카카오 REST API 키는 브라우저에 노출되면
안 되는 민감한 인증 정보라서(카카오 공식 문서에서도 서버 호출을 권장한다), 검색
요청을 프론트엔드가 아니라 이 서버가 대신 카카오에 보낸다. 반대로 지도를 그리는
"JavaScript 키"는 원래도 브라우저에 노출되는 것을 전제로 하는 키(대신 카카오
콘솔에 등록한 도메인에서만 동작)라서, /api/config를 통해 프론트엔드에 그대로
내려준다.
"""

import os
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
    """두 좌표 사이의 실제 대중교통(도보+버스+지하철) 경로를 ODsay API로 조회한다.
    프론트엔드는 지금까지 두 지점의 직선거리(haversine)만 보여줬는데, 이 엔드포인트가
    붙으면 실제 소요시간·요금·구간별(도보/버스/지하철) 경로로 대체할 수 있다."""

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

    # ODsay는 HTTP 200이어도 좌표 근처에 정류장이 없거나 키가 잘못된 경우 에러를
    # 함께 200에 담아 보낸다. 실제로 겪어보니 이 "error" 필드가 단일 객체가 아니라
    # 리스트({"error": [{"code": ..., "message": ...}]})로 오는 경우가 있어서,
    # 어떤 모양으로 와도 죽지 않도록 방어적으로 파싱한다.
    if "error" in data:
        err = data["error"]
        err_item = err[0] if isinstance(err, list) and err else err
        if isinstance(err_item, dict):
            err_msg = err_item.get("message") or err_item.get("msg") or str(err_item)
        else:
            err_msg = str(err_item)
        raise HTTPException(
            status_code=502,
            detail=f"ODsay 경로 탐색에 실패했습니다: {err_msg}",
        )

    paths = data.get("result", {}).get("path", [])
    if not paths:
        return {"found": False, "legs": [], "totalTime": None, "payment": None, "totalDistance": None}

    best = paths[0]  # OPT=0(추천경로) 기준 정렬의 첫 번째 결과
    info = best.get("info", {})

    legs = []
    for sub in best.get("subPath", []):
        traffic_code = sub.get("trafficType")
        mode = ODSAY_TRAFFIC_TYPE.get(traffic_code, f"unknown({traffic_code})")
        leg = {
            "mode": mode,
            "sectionTime": sub.get("sectionTime"),  # 분
            "distance": sub.get("distance"),  # 미터
            "startName": sub.get("startName"),
            "endName": sub.get("endName"),
        }
        lanes = sub.get("lane") or []
        if mode == "bus" and lanes:
            leg["routeName"] = ", ".join(sorted({str(l.get("busNo", "")) for l in lanes if l.get("busNo")}))
        elif mode == "subway" and lanes:
            leg["routeName"] = ", ".join(sorted({str(l.get("name", "")) for l in lanes if l.get("name")}))
        legs.append(leg)

    return {
        "found": True,
        "totalTime": info.get("totalTime"),  # 분
        "payment": info.get("payment"),  # 원
        "totalDistance": info.get("totalDistance"),  # 미터
        "busTransitCount": info.get("busTransitCount"),
        "subwayTransitCount": info.get("subwayTransitCount"),
        "legs": legs,
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
