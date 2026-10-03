import { defineConfig } from '@playwright/test'

// The UI runs in Edge, the same engine as the WebView2 the Tauri shell uses,
// against the real Python engine (see e2e/servers.mjs). Tests share that one
// engine, so they run in order on a single worker.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:1431',
    channel: 'msedge',
    viewport: { width: 1440, height: 900 },
    locale: 'pt-BR',
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'node e2e/servers.mjs',
      url: 'http://127.0.0.1:8793/api/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:1431',
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        STZ_E2E_ENGINE: 'http://127.0.0.1:8793',
        VITE_BRIDGE_URL: 'http://localhost:1431',
        VITE_BRIDGE_TOKEN: 'e2e-token',
      },
    },
  ],
})
