import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { crx } from '@crxjs/vite-plugin'
import manifest from './manifest.json'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    crx({ manifest }), 
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5175,
    strictPort: true,
    // 👇 Vite 5.x로 내려왔기 때문에 이 표준 설정들이 드디어 정상 작동합니다!
    cors: true,
    origin: 'http://localhost:5175',
    proxy: {
      '/extension': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  },
})