/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev the SPA is served at http://app-a.localhost:5173 and everything App A owns
// (/api, /rp) is proxied to the backend. The Host header is kept, so the backend knows
// the request is for App A. The IdP and App B are opened directly on *.localhost:8000.
const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    allowedHosts: ['app-a.localhost'],
    proxy: {
      '/api': { target: backend },
      '/rp': { target: backend },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
