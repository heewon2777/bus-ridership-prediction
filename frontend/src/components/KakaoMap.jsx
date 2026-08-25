import { useEffect, useRef } from 'react';

const MARKER_COLOR = { origin: '#2A5FE0', dest: '#C7343E' };
const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 }; // 서울시청 기준

// 카카오맵 인스턴스, 마커(CustomOverlay), 직선(Polyline)은 모두 React 상태가
// 아니라 카카오 SDK의 명령형(imperative) 객체라서, useState 대신 ref에 담아두고
// picked(선택된 출발지/목적지)가 바뀔 때마다 useEffect에서 직접 그려준다.
export default function KakaoMap({ kakaoLoaded, picked }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({ origin: null, dest: null });
  const polylineRef = useRef(null);

  // 지도 초기화 (SDK 로드 완료 후 한 번만)
  useEffect(() => {
    if (!kakaoLoaded || !containerRef.current || mapRef.current) return;
    const { kakao } = window;
    mapRef.current = new kakao.maps.Map(containerRef.current, {
      center: new kakao.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
      level: 7
    });
  }, [kakaoLoaded]);

  // 마커 + 직선 다시 그리기
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.kakao) return;
    const { kakao } = window;

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

    if (polylineRef.current) {
      polylineRef.current.setMap(null);
      polylineRef.current = null;
    }

    if (picked.origin && picked.dest) {
      const p1 = new kakao.maps.LatLng(picked.origin.lat, picked.origin.lng);
      const p2 = new kakao.maps.LatLng(picked.dest.lat, picked.dest.lng);
      const polyline = new kakao.maps.Polyline({
        path: [p1, p2],
        strokeWeight: 3,
        strokeColor: '#5B6472',
        strokeOpacity: 0.9,
        strokeStyle: 'shortdash'
      });
      polyline.setMap(map);
      polylineRef.current = polyline;

      const bounds = new kakao.maps.LatLngBounds();
      bounds.extend(p1);
      bounds.extend(p2);
      map.setBounds(bounds, 60);
    }
  }, [picked]);

  return <div id="map" ref={containerRef} />;
}
