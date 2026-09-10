import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';

// 개발 중에는 프론트(Vite, 기본 5173포트)가 /api로 시작하는 요청을 전부
// FastAPI 백엔드(기본 8000포트)로 그대로 넘겨준다. 그래서 프론트 코드에서는
// 그냥 fetch('/api/search?...')만 하면 되고, 백엔드 주소를 따로 신경 쓸
// 필요도, CORS 설정도 신경 쓸 필요가 없다.
//
// `npm run dev:phone`(--mode phone)으로 띄우면 HTTPS + LAN 노출을 켠다.
// 브라우저는 https가 아니면 위치 정보(geolocation)를 아예 막기 때문에, 휴대폰에서
// "현재 위치" 버튼을 쓰려면 이 모드가 필요하다. 인증서는 자체 서명이라 휴대폰에서
// 처음 접속할 때 경고를 한 번 통과해야 한다 (README "휴대폰에서 열기" 참고).
// 휴대폰이 보내는 /api 요청도 이 프록시가 PC 안에서 백엔드로 넘겨주므로,
// 백엔드는 그대로 localhost:8000에 떠 있으면 된다.
export default defineConfig(({ mode }) => {
  const forPhone = mode === 'phone';
  return {
    plugins: [react(), forPhone && basicSsl()].filter(Boolean),
    server: {
      host: forPhone, // true면 LAN(0.0.0.0)에도 열린다. 기본은 localhost만.
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true
        }
      }
    }
  };
});
