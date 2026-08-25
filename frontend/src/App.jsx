import { useEffect, useMemo, useState } from 'react';
import SearchField from './components/SearchField.jsx';
import KakaoMap from './components/KakaoMap.jsx';
import { loadKakaoSdk } from './lib/kakao.js';
import { haversineMeters, formatDistance } from './lib/geo.js';

export default function App() {
  const [kakaoLoaded, setKakaoLoaded] = useState(false);
  const [configWarning, setConfigWarning] = useState('');
  const [picked, setPicked] = useState({ origin: null, dest: null });

  // 부트스트랩: 백엔드에서 설정(JS 키)을 받아와 카카오맵 SDK를 로드한다.
  useEffect(() => {
    let cancelled = false;

    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => {
        if (cancelled) return;
        if (!cfg.kakaoJsKey) {
          setConfigWarning(
            'KAKAO_JS_KEY가 설정되지 않았습니다. backend/.env.example을 backend/.env로 복사하고 실제 카카오 JavaScript 키를 넣은 뒤 백엔드를 다시 시작하세요.'
          );
          return;
        }
        loadKakaoSdk(cfg.kakaoJsKey)
          .then(() => {
            if (!cancelled) setKakaoLoaded(true);
          })
          .catch(() => {
            if (!cancelled) {
              setConfigWarning(
                '카카오맵 SDK 로드에 실패했습니다. JavaScript 키가 올바른지, 카카오 디벨로퍼스에 이 도메인이 "플랫폼 > Web"으로 등록되어 있는지 확인하세요.'
              );
            }
          });
      })
      .catch(() => {
        if (!cancelled) {
          setConfigWarning('백엔드(/api/config)에 연결할 수 없습니다. FastAPI 서버(backend/main.py)가 실행 중인지 확인하세요.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const distanceLabel = useMemo(() => {
    if (!picked.origin || !picked.dest) return null;
    return formatDistance(haversineMeters(picked.origin, picked.dest));
  }, [picked.origin, picked.dest]);

  return (
    <div className="page">
      <header>
        <p className="eyebrow">버스 예측 프로젝트 · 실제 지도 연동 프로토타입 (React + FastAPI)</p>
        <h1>내가 과연 탈 수 있을까? — 진짜 지도로</h1>
        <p className="sub">
          기존 데모(Claude Artifact)는 보안 정책상 외부 API를 전혀 호출할 수 없어 가상의 동네
          지도를 썼습니다. 이 페이지는 React 프론트엔드 + FastAPI 백엔드로 실제 카카오맵과 실제
          장소 검색을 붙였습니다.
        </p>
      </header>

      {configWarning && <div className="config-warning show">{configWarning}</div>}

      <section className="panel">
        <h2>1. 출발지 · 목적지 검색 (실제 카카오 장소 검색)</h2>
        <div className="picker-row">
          <SearchField
            label="출발지"
            dotClass="origin"
            placeholder="예: 강남역, 동탄2신도시 환승센터"
            onSelect={(place) => setPicked((p) => ({ ...p, origin: place }))}
          />
          <SearchField
            label="목적지"
            dotClass="dest"
            placeholder="예: 판교역, 회사 이름"
            onSelect={(place) => setPicked((p) => ({ ...p, dest: place }))}
          />
        </div>

        <KakaoMap kakaoLoaded={kakaoLoaded} picked={picked} />

        {distanceLabel && (
          <div className="distance-line">
            두 지점 사이 직선거리 약 <b>{distanceLabel}</b> · 실제 도보+버스 경로는 ODsay API
            연동 시 대체될 예정입니다.
          </div>
        )}

        <p className="footnote inline">
          검색은 이 페이지가 아니라 백엔드(<code>backend/main.py</code>)가 카카오 로컬 API를
          대신 호출해서 결과만 돌려줍니다 — REST API 키가 브라우저에 노출되지 않습니다. 두
          지점을 모두 고르면 지도에 직선을 그어 직선거리를 보여주는데, 실제 도보+버스
          경로(ODsay 연동)는 다음 단계입니다.
        </p>
      </section>

      <p className="footnote">
        설정 방법은 README.md를 참고하세요. (카카오 디벨로퍼스에서 앱 생성 → JavaScript 키 /
        REST API 키 발급 → backend/.env에 입력 → 백엔드 · 프론트엔드 각각 실행)
      </p>
    </div>
  );
}
