# 내가 과연 탈 수 있을까 — 실제 지도 연동 프로토타입 (React + FastAPI)

기존 웹앱 데모는 Claude Artifact로 게시돼 있어서, 보안 정책(CSP)상 구글 폰트를 제외한
어떤 외부 요청(지도 SDK, API 호출 등)도 브라우저에서 직접 할 수 없습니다. 그래서 가상의
동네 지도 + 로컬 검색으로 UX와 계산 로직만 시연했습니다.

이 폴더는 그 다음 단계 — **실제 카카오맵과 실제 장소 검색을 붙이는 작업**의 출발점입니다.
프론트엔드는 **React(Vite)**, 백엔드는 **FastAPI(Python)**로 구성했습니다.

## 이 프로토타입이 하는 일

- 실제 **카카오맵**을 화면에 띄웁니다 (카카오맵 JavaScript SDK).
- 출발지·목적지 검색창에 장소명을 입력하면, **카카오 로컬 API(키워드 장소 검색)**로
  실제 장소를 찾아 드롭다운으로 보여줍니다.
- 검색 결과를 고르면 지도에 마커가 찍히고, 두 지점을 모두 고르면 직선을 긋고
  직선거리를 계산해서 보여줍니다. (실제 도보+버스 경로는 ODsay API 연동이 필요한
  다음 단계이며, 아직 포함되어 있지 않습니다 — 아래 "다음 단계" 참고.)
- 카카오 REST API 키는 브라우저에 절대 노출되지 않습니다. FastAPI 백엔드가 대신
  카카오 API를 호출해주는 프록시 역할을 합니다 (카카오 공식 문서도 REST API 키는
  서버에서만 쓰라고 권장합니다).

## 폴더 구성

```
bus-predictor-real-map-react/
├── backend/                  # FastAPI 백엔드
│   ├── main.py                #   /api/config, /api/search 라우트 + (배포 시) 프론트 정적 서빙
│   ├── requirements.txt
│   ├── .env.example           #   이 파일을 .env로 복사해서 실제 카카오 키를 채워넣으세요
│   └── .gitignore
└── frontend/                  # React(Vite) 프론트엔드
    ├── index.html
    ├── package.json
    ├── vite.config.js         #   /api 요청을 백엔드(8000번 포트)로 프록시
    └── src/
        ├── main.jsx
        ├── App.jsx             # 전체 화면 구성
        ├── index.css
        ├── components/
        │   ├── SearchField.jsx # 검색창 + 자동완성 드롭다운 (출발지/목적지 공용)
        │   └── KakaoMap.jsx    # 카카오맵 렌더링 + 마커/직선 갱신
        └── lib/
            ├── kakao.js        # 카카오맵 SDK 동적 로드 헬퍼
            └── geo.js          # 두 지점 사이 직선거리(하버사인 공식) 계산
```

## 준비물: 카카오 API 키 발급받기

1. [카카오 디벨로퍼스](https://developers.kakao.com)에 카카오 계정으로 로그인합니다.
2. "내 애플리케이션 → 애플리케이션 추가하기"로 앱을 하나 만듭니다 (이름은 아무거나, 예:
   `bus-predictor`).
3. 앱 생성 후 **앱 키** 메뉴에서 다음 두 개를 확인합니다.
   - **JavaScript 키** → 실제 지도를 그리는 데 씁니다.
   - **REST API 키** → 장소 검색(지오코딩)에 씁니다.
4. **플랫폼 설정**으로 이동해 "Web" 플랫폼을 추가하고, 사이트 도메인에
   `http://localhost:5173` (프론트엔드 개발 서버 주소)을 등록합니다. 나중에 실제
   서버에 배포하면 그 도메인도 여기에 추가해야 지도가 뜹니다.

## 실행 방법 (개발 모드 — 터미널 두 개 사용)

### 1) 백엔드 (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows는 .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` 파일을 열어서 `KAKAO_JS_KEY`, `KAKAO_REST_API_KEY`를 방금 발급받은 값으로
채워넣은 다음:

```bash
python main.py
```

`Uvicorn running on http://0.0.0.0:8000`이 뜨면 백엔드 준비 완료입니다.
(`uvicorn main:app --reload --port 8000` 명령으로 실행해도 동일합니다.)

### 2) 프론트엔드 (React/Vite) — 새 터미널에서

```bash
cd frontend
npm install
npm run dev
```

터미널에 뜨는 주소(기본 `http://localhost:5173`)를 브라우저에서 열면, 실제 카카오
지도가 뜨고 검색창에 장소명을 입력하면 진짜 검색 결과가 나옵니다. 프론트엔드가 보내는
`/api/...` 요청은 `vite.config.js`의 프록시 설정을 통해 자동으로 백엔드(8000번 포트)로
전달되므로, 두 서버가 서로 다른 포트에 떠 있어도 별도 CORS 설정 없이 그냥 동작합니다.

## 배포용으로 합쳐서 서버 하나로 띄우기 (선택)

개발할 때는 두 서버를 따로 띄우지만, 실제로 배포할 때는 프론트엔드를 빌드해서
FastAPI 백엔드 하나가 전부 서빙하게 만들 수도 있습니다.

```bash
cd frontend
npm run build        # frontend/dist 에 정적 파일 생성

cd ../backend
source .venv/bin/activate
python main.py        # frontend/dist가 있으면 자동으로 함께 서빙합니다
```

이 경우 `http://localhost:8000` 하나만 열면 되고, 이 도메인을 카카오 디벨로퍼스의
"플랫폼 > Web"에 등록해야 합니다. (실제 서버에 올릴 때는 그 서버의 도메인을 등록하세요.)

## 왜 굳이 백엔드가 필요한가요?

- **REST API 키(장소 검색)**: 카카오 공식 문서에서도 REST API 키는 인증 정보이므로
  브라우저에 노출하지 말고 서버에서 호출하라고 안내합니다. 그래서 프론트엔드는
  카카오를 직접 호출하지 않고, 우리 백엔드의 `/api/search`만 호출합니다.
- **JavaScript 키(지도 표시)**: 이 키는 원래 브라우저에 노출되는 것을 전제로 하지만,
  카카오 디벨로퍼스에 등록한 도메인에서만 동작하도록 제한됩니다. 이 프로토타입에서는
  `.env` 한 곳에서만 관리하도록 `/api/config`로 내려주는 방식을 썼습니다 (키를
  프론트엔드 코드에 직접 하드코딩하지 않기 위해서입니다).
- Claude Artifact 안에서는 이런 서버 자체를 둘 수 없고, 브라우저에서 외부로 나가는
  요청도 전부 막혀 있어서 이번 작업은 Artifact 밖으로 나와야 했습니다.

## 다음 단계 (기획서 로드맵과 연결)

프로젝트 기획서(`기획/프로젝트_기획서.md`) 6장 로드맵 기준으로, 이 프로토타입 다음에
이어질 작업들입니다.

- **ODsay 대중교통 길찾기 API 연동**: 지금은 두 지점 사이 직선거리만 보여주는데,
  이 자리(백엔드에 `/api/route` 같은 엔드포인트를 추가)에 ODsay API를 붙이면 실제
  도보+버스 경로와 소요시간이 나옵니다.
- **TAGO/서울시 BIS 버스도착정보 API 연동**: 실제 정류장의 다음 버스 도착 예정시간을
  가져와 정시 도착 확률 계산에 사용합니다.
- **혼잡도 모델(GBM) 결과 연결**: `bus_congestion_pipeline.py`가 만든
  `congestion_lookup.json`을 FastAPI 백엔드가 읽어서, 좌석 여유 확률도 실제 학습
  결과로 대체합니다.
- 이 세 가지가 붙으면 기존 Artifact 데모의 계산 로직(정시 도착 확률 × 좌석 여유
  확률, "근거 보기" 패널 포함)을 이 실제 서버·지도 위에 React 컴포넌트로 옮겨
  완성된 형태가 됩니다.

## 검증한 것 / 검증하지 못한 것

이 환경에서 직접 실행해 확인한 것: 백엔드 `pip install` → 서버 기동 → `/api/config`,
`/api/search`(REST 키 미설정 시 안내 메시지가 정확히 뜨는지) 확인, 프론트엔드
`npm install` → `npm run build`(빌드 오류 없음) → `npm run dev`로 실제 개발 서버를
띄워 브라우저에서 설정 경고와 검색 오류 메시지가 정상적으로 표시되는지까지 Playwright로
확인했습니다. 다만 이 환경에서는 카카오 서버로 나가는 실제 네트워크 호출을 테스트할 수
없었기 때문에, 실제 카카오 API 키로 지도가 정상적으로 뜨는지와 검색 결과가 정확한지는
발급받은 키로 직접 실행해서 확인해야 합니다.
