// Starts what the UI tests talk to: a fake Ollama and the real Python engine.
// The engine gets its own data directory, so a test run never touches the
// user's config, glossary or checkpoints.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const work = path.join(here, '.tmp')
const OLLAMA_PORT = 8794
const ENGINE_PORT = 8793

fs.rmSync(work, { recursive: true, force: true })
fs.mkdirSync(path.join(work, 'files'), { recursive: true })
fs.copyFileSync(path.join(here, 'fixtures', 'items.xml'), path.join(work, 'files', 'items.xml'))

// Fake Ollama: answers /api/generate by prefixing every text with [PT].
const between = (text, start, end) => text.slice(text.indexOf(start) + start.length, text.lastIndexOf(end))
http
  .createServer((request, response) => {
    let body = ''
    request.on('data', (chunk) => (body += chunk))
    request.on('end', () => {
      let answer = {}
      if (request.method === 'POST') {
        const { prompt } = JSON.parse(body)
        if (prompt.includes('"inputs"')) {
          const { inputs } = JSON.parse(between(prompt, 'Input: ', '[/INST]'))
          answer = { translations: inputs.map((item) => `[PT] ${item.text}`) }
        } else {
          answer = { text: `[PT] ${JSON.parse(between(prompt, 'Input:\n', '\n\nOutput:')).text}` }
        }
      }
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ response: JSON.stringify(answer) }))
    })
  })
  .listen(OLLAMA_PORT, '127.0.0.1')

const python = process.env.STZ_PYTHON || path.join(repo, '.venv', 'Scripts', 'python.exe')
const engine = spawn(python, ['-m', 'engine', '--port', String(ENGINE_PORT), '--parent-pid', String(process.pid)], {
  cwd: repo,
  stdio: 'inherit',
  env: {
    ...process.env,
    STZ_XML_TRANSLATOR_DATA_DIR: path.join(work, 'data'),
    // runtime.json goes under LocalAppData: keep it out of the real one.
    LOCALAPPDATA: path.join(work, 'local'),
    STZ_XML_BRIDGE_TOKEN: 'e2e-token',
    OLLAMA_HOST: `http://127.0.0.1:${OLLAMA_PORT}`,
    PYTHONIOENCODING: 'utf-8',
  },
})
engine.on('exit', (code) => process.exit(code ?? 1))
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => process.exit(0))
