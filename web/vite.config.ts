import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 개발 시 Vite 프록시로 백엔드(COURSESPEC_WEB_PORT, 기본 18080)에 붙는다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 15180,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
