import { expect, test } from '@playwright/test'

// The real HTTP engine is shared with the flow tests. Only Tauri lifecycle IPC
// is mocked here; native restart/exit behavior is covered by Rust and build probes.
test('an exhausted startup shows the cause and manual retry reaches the engine', async ({ page }) => {
  await page.addInitScript(() => {
    const status = { phase: 'failed', reason: 'missing', attempts: 4, generation: 0, logPath: 'C:/diagnostics/engine.log' }
    Object.assign(window, {
      isTauri: true,
      __TAURI_INTERNALS__: {
        invoke: async (command: string) => {
          if (command === 'engine_status') return { ...status }
          if (command === 'bridge_info') return { baseUrl: window.location.origin, token: 'e2e-token' }
          if (command === 'retry_engine') {
            Object.assign(status, { phase: 'ready', reason: '', attempts: 1, generation: 1 })
            return
          }
          throw new Error(`Unexpected IPC: ${command}`)
        },
      },
    })
  })
  await page.goto('/')
  const failure = page.getByRole('alert')
  await expect(failure).toContainText('Não foi possível iniciar o motor de tradução.')
  await expect(failure).toContainText('Reinstale o aplicativo.')
  await expect(failure).toContainText('C:/diagnostics/engine.log')
  await failure.getByRole('button', { name: 'Tentar novamente' }).click()
  await expect(failure).toBeHidden()
  await expect(page.getByRole('button', { name: 'Configurações' })).toBeVisible()
})

test('a restarted engine replaces stale state even when its revision repeats', async ({ page }) => {
  const response = await page.request.get('/api/state', { headers: { Authorization: 'Bearer e2e-token' } })
  const snapshot = await response.json()
  await page.route('**/api/state', (route) => route.fulfill({ json: snapshot }))
  await page.addInitScript(() => {
    const status = { phase: 'ready', reason: '', attempts: 1, generation: 1, logPath: '' }
    Object.assign(window, {
      recoveryStatus: status, isTauri: true,
      __TAURI_INTERNALS__: { invoke: async (command: string) => {
        if (command === 'engine_status') return { ...status }
        if (command === 'bridge_info') return { baseUrl: window.location.origin, token: 'e2e-token' }
        throw new Error(`Unexpected IPC: ${command}`)
      } },
    })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Configurações' })).toBeVisible()
  // Keep the revision identical: an epoch change must still discard the old XML.
  snapshot.loaded = false
  snapshot.file = null
  snapshot.total = 0
  await page.evaluate(() => {
    const current = window as unknown as { recoveryStatus: { generation: number } }
    current.recoveryStatus.generation = 2
  })
  await expect(page.getByRole('heading', { name: 'Projetos', exact: true })).toBeVisible()
})
