// Installed-app acceptance: real Tauri IPC, WebView2, and frozen engine.
// Run: node desktop/e2e/native-recovery.mjs <installed stz-xml-translator.exe>
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { chromium } from '@playwright/test'

const executable = path.resolve(process.argv[2] ?? '')
assert.equal(path.basename(executable), 'stz-xml-translator.exe')
assert.ok(fs.existsSync(executable))
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'stz-installed-probe-'))
const fixture = path.join(work, 'items.xml')
fs.copyFileSync(path.join(import.meta.dirname, 'fixtures/items.xml'), fixture)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function until(check, timeout = 25_000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const result = await check()
    if (result) return result
    await sleep(200)
  }
  throw new Error('Installed-app probe timed out')
}

async function launch(program, name) {
  const local = path.join(work, name)
  fs.mkdirSync(local, { recursive: true })
  const server = net.createServer()
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise((resolve) => server.close(resolve))
  const child = spawn(program, [], {
    cwd: local, windowsHide: true, stdio: 'ignore',
    env: {
      ...process.env, LOCALAPPDATA: local,
      STZ_XML_TRANSLATOR_DATA_DIR: path.join(local, 'data'),
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1`,
    },
  })
  const runtime = path.join(local, 'STZ XML Translator/logs', `engine-${child.pid}.json`)
  const statusPath = runtime.replace(/\.json$/, '.status.json')
  const status = () => {
    try { return JSON.parse(fs.readFileSync(statusPath, 'utf8')) } catch { return null }
  }
  const currentRuntime = () => JSON.parse(fs.readFileSync(runtime, 'utf8'))
  let browser
  try {
    await until(async () => {
      try { return (await fetch(`http://127.0.0.1:${port}/json/version`)).ok } catch { return false }
    })
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`)
    const page = await until(() => browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().includes('tauri.localhost')))
    const api = async (url, body) => {
      const rt = currentRuntime()
      const response = await fetch(`http://127.0.0.1:${rt.port}${url}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${rt.token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      assert.ok(response.ok, `Engine request failed: ${url} (${response.status})`)
      return response.json()
    }
    return { child, browser, page, runtime, status, currentRuntime, api }
  } catch (error) {
    if (browser) await browser.close()
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    throw error
  }
}

async function close(app) {
  await app.page.evaluate(() => window.__TAURI_INTERNALS__.invoke('quit')).catch(() => {})
  await until(() => app.child.exitCode !== null)
  await app.browser.close()
  assert.equal(app.status().phase, 'stopped')
  assert.ok(!fs.existsSync(app.runtime), 'Runtime removed on close')
}

let active
try {
  active = await launch(executable, 'installed')
  await until(() => active.status()?.phase === 'ready')
  await active.page.getByRole('heading', { name: 'Abra um arquivo XML' }).waitFor()
  console.log('PASS: installed release opens its UI and frozen engine')

  const load = async () => {
    await active.api('/api/xml/open', { path: fixture })
    await active.api('/api/xml/load', { parent: 'item', targets: ['description'], contexts: ['name'] })
  }
  await load()
  const entries = await active.api('/api/entries')
  await active.api('/api/entries/edit', { id: entries.entries[0].id, text: 'Checkpoint de teste' })
  await active.page.getByText('Checkpoint de teste', { exact: true }).first().waitFor()
  const initial = active.status().generation
  process.kill(active.currentRuntime().pid)
  await until(() => active.status()?.phase === 'ready' && active.status().generation > initial)
  await active.page.getByRole('heading', { name: 'Abra um arquivo XML' }).waitFor()
  await load()
  const restored = await active.api('/api/entries')
  assert.equal(restored.entries[0].translation, 'Checkpoint de teste')
  console.log('PASS: real engine termination triggers restart and checkpoint restoration')

  for (let generation = active.status().generation; generation < 4; generation++) {
    process.kill(active.currentRuntime().pid)
    await until(() => active.status()?.phase === 'ready' && active.status().generation > generation)
  }
  process.kill(active.currentRuntime().pid)
  await until(() => active.status()?.phase === 'failed')
  await active.page.getByRole('alert').getByText('Não foi possível iniciar o motor de tradução.').waitFor()
  assert.equal(active.status().attempts, 4)
  assert.match(fs.readFileSync(active.status().logPath, 'utf8'), /Engine exited:/)
  await active.page.getByRole('button', { name: 'Tentar novamente' }).click()
  await until(() => active.status()?.phase === 'ready')
  await active.page.getByRole('heading', { name: 'Abra um arquivo XML' }).waitFor()
  console.log('PASS: retries stop at their limit; diagnostic screen and manual retry work')
  await close(active)
  active = null

  // Do not alter installed files to test a missing bundled engine.
  const bare = path.join(work, 'bare')
  fs.mkdirSync(bare)
  const bareExe = path.join(bare, 'stz-xml-translator.exe')
  fs.copyFileSync(executable, bareExe)
  active = await launch(bareExe, 'missing')
  await until(() => active.status()?.phase === 'failed')
  assert.equal(active.status().reason, 'missing')
  await active.page.getByRole('alert').getByText('O arquivo do motor não foi encontrado. Reinstale o aplicativo.').waitFor()
  console.log('PASS: release with missing engine shows a specific error after bounded retries')
  await close(active)
  active = null
  console.log(`PASS: graceful shutdown removes runtime records. Diagnostics: ${work}`)
} finally {
  if (active) {
    await active.browser.close().catch(() => {})
    spawnSync('taskkill.exe', ['/PID', String(active.child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
  }
}
