import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// 개발 중에는 /api 요청을 FastAPI(8000)로 넘긴다. 브라우저 입장에서는 같은 출처이므로
// 쿠키 인증이 그대로 동작하고 CORS 설정이 필요 없다. 운영에서는 nginx 가 같은 역할을 한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.PORT) || 5173, // PORT 환경변수가 있으면 그 포트 사용
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
