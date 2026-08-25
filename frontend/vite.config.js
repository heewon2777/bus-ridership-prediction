import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 개발 중에는 프론트(Vite, 기본 5173포트)가 /api로 시작하는 요청을 전부
// FastAPI 백엔드(기본 8000포트)로 그대로 넘겨준다. 그래서 프론트 코드에서는
// 그냥 fetch('/api/search?...')만 하면 되고, 백엔드 주소를 따로 신경 쓸
// 필요도, CORS 설정도 신경 쓸 필요가 없다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
});
