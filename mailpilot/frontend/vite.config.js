import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В dev-режиме фронт (Vite :5173) проксирует /api на FastAPI (:8000).
// В проде FastAPI сам отдаёт собранный dist/, поэтому запросы идут на тот же origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
