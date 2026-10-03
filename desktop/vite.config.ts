import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'

// The UI tests run on their own port, so they never collide with a running
// `tauri dev`, and reach the engine through this server (same origin, no CORS).
const e2eEngine = process.env.STZ_E2E_ENGINE

// Tauri expects a fixed dev port and keeps its own output on screen.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  clearScreen: false,
  server: {
    port: e2eEngine ? 1431 : 1420,
    strictPort: true,
    watch: { ignored: ['**/src-tauri/**', '**/e2e/.tmp/**'] },
    proxy: e2eEngine ? { '/api': e2eEngine } : undefined,
  },
})
