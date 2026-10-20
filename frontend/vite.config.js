import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies the API and the WebSocket so the browser sees ONE origin (cookies just work).
const backend = process.env.VITE_BACKEND || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: false },
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true, changeOrigin: false },
    },
  },
});
