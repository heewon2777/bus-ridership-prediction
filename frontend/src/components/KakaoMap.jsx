import { useEffect, useRef } from 'react';

const MARKER_COLOR = { origin: '#2A5FE0', dest: '#C7343E' };
const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 }; // 서울시청 기준

// 구간(도보/버스/지하철)별 선 스타일. 도보만 점선으로 구분한다.
const LEG_STYLE = {
  walk: { strokeColor: '#5B6472', strokeStyle: 'shortdash', strokeWeight: 4 },
  bus: { strokeColor: '#2A5FE0', strokeStyle: 'solid', strokeWeight: 6 },
  subway: { strokeColor: '#00A05A', strokeStyle: 'solid', strokeWeight: 6 }
};
const FALLBACK_LEG_STYLE = { strokeColor: '#8A93A0', strokeStyle: 'solid', strokeWeight: 5 };

// 카카오맵 인스턴스, 마커(CustomOverlay), 경로선(Polyline)은 모두 React 상태가
// 아니라 카카오 SDK의 명령형(imperative) 객체라서, useState 대신 ref에 담아두고
// picked/path(선택된 경로)가 바뀔 때마다 useEffect에서 직접 그려준다.
export default function KakaoMap({ kakaoLoaded, picked, path }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({ origin: null, dest: null });
  const polylinesRef = useRef([]);

  // 지도 초기화 (SDK 로드 완료 후 한 번만)
  useEffect(() => {
    if (!kakaoLoaded || !containerRef.current || mapRef.current) return;
    const { kakao } = window;
    mapRef.current = new kakao.maps.Map(containerRef.current, {
      center: new kakao.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
      level: 7
    });
  }, [kakaoLoaded]);

  // 마커 + 경로선 다시 그리기
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.kakao) return;
    const { kakao } = window;

    // 그릴 좌표가 2개 이상인 구간만 실제 경로로 인정한다. 경로 조회 전이거나
    // 좌표가 안 온 경우에는 아래에서 출발-목적지 직선으로 되돌아간다.
    const drawableLegs = (path?.legs ?? []).filter((leg) => (leg.path?.length ?? 0) >= 2);

    ['origin', 'dest'].forEach((field) => {
      if (markersRef.current[field]) {
        markersRef.current[field].setMap(null);
        markersRef.current[field] = null;
      }
      const place = picked[field];
      if (!place) return;

      const pos = new kakao.maps.LatLng(place.lat, place.lng);
      const dot = document.createElement('div');
      dot.style.cssText = `width:16px;height:16px;border-radius:50%;background:${MARKER_COLOR[field]};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`;
      const overlay = new kakao.maps.CustomOverlay({ position: pos, content: dot, yAnchor: 0.5 });
      overlay.setMap(map);
      markersRef.current[field] = overlay;
      map.panTo(pos);
    });

    polylinesRef.current.forEach((line) => line.setMap(null));
    polylinesRef.current = [];

    // 실제 경로가 있으면 구간별로 그리고, 없으면(조회 전·실패) 예전처럼
    // 출발-목적지 참고용 직선 하나만 긋는다.
    let linesToDraw = drawableLegs.map((leg) => ({
      points: leg.path,
      style: LEG_STYLE[leg.mode] ?? FALLBACK_LEG_STYLE
    }));
    if (linesToDraw.length === 0 && picked.origin && picked.dest) {
      linesToDraw = [{ points: [picked.origin, picked.dest], style: LEG_STYLE.walk }];
    }

    const bounds = new kakao.maps.LatLngBounds();
    linesToDraw.forEach(({ points, style }) => {
      const latLngs = points.map((p) => new kakao.maps.LatLng(p.lat, p.lng));
      const line = new kakao.maps.Polyline({ path: latLngs, strokeOpacity: 0.9, ...style });
      line.setMap(map);
      polylinesRef.current.push(line);
      latLngs.forEach((pt) => bounds.extend(pt));
    });

    if (linesToDraw.length > 0) map.setBounds(bounds, 60);
  }, [picked, path]);

  return <div id="map" ref={containerRef} />;
}
