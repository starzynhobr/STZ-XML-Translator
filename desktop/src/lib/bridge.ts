import { invoke, isTauri } from '@tauri-apps/api/core'
import { useCallback, useEffect, useRef, useState } from 'react'

export type Status = 'pending' | 'translating' | 'translated' | 'confirmed' | 'error'
export type Theme = 'dark' | 'light' | 'system'
export type Accent = 'teal' | 'blue' | 'amber'

export interface Entry {
  id: string
  n: number
  original: string
  translation: string
  status: Status
  sourceTag: string
  /** Record tag the entry belongs to, e.g. "villain". */
  group: string
  context: Record<string, string>
  error: string
}

/** One saved change of an entry: what it became and where the change came from. */
export interface Version {
  oldText: string
  newText: string
  oldStatus: Status
  newStatus: Status
  source: 'ai' | 'manual' | 'confirm' | 'import' | 'edit' | 'reset' | 'memory' | 'agent'
  at: number
}

/** A translation the same original already has somewhere in the game. */
export interface Suggestion {
  translation: string
  confirmed: boolean
  uses: number
}

export interface SearchResult {
  file: string
  path: string
  xpath: string
  original: string
  translation: string
  status: Status
}

let pendingSearch = ''

/** Hands a search text from the project screen to the bench that opens next. */
export function setPendingSearch(text: string) {
  pendingSearch = text
}

export function takePendingSearch(): string {
  const text = pendingSearch
  pendingSearch = ''
  return text
}

export interface Provider {
  id: string
  needsKey: boolean
  hasKey: boolean
  ai: boolean
  keyUrl: string
}

export interface Settings {
  provider: string
  providers: Provider[]
  locale: string
  locales: Record<string, string>
  target: string
  targets: Record<string, string>
  ollamaModel: string
  ollamaThinking: boolean
  azureRegion: string
  context: string
  models: { label: string; paid: boolean }[]
  model: string
  theme: Theme
  accent: Accent
  autoUpdate: boolean
  glossaryCount: number
}

export interface UpdateInfo {
  current: string
  status: 'idle' | 'checking' | 'downloading' | 'ready' | 'error'
  error: string
  progress: number
  available: boolean
  version: string
  notes: string
  pageUrl: string
  checkedAt: number
}

export interface LogLine {
  at: number
  text: string
  level: 'info' | 'error'
}

export interface EngineState {
  version: string
  rev: number
  file: { path: string; name: string } | null
  parents: string[]
  structure: { parent: string; targets: string[]; contexts: string[]; groups: Group[] } | null
  project: { id: string; name: string; folder: string } | null
  loaded: boolean
  total: number
  counts: Record<Status, number>
  xmlBusy: boolean
  translating: boolean
  translatingEntries: string[]
  activity: LogLine | null
  log: LogLine[]
  settings: Settings
  update: UpdateInfo
  import: ImportState
}

/** Comparing a clean copy of the game with the hand-edited XMLs. */
export interface ImportState {
  status: 'idle' | 'running' | 'ready' | 'error'
  folder?: string
  done?: number
  total?: number
  files?: { file: string; texts: number; found: number; problem: '' | 'missing' | 'invalid' }[]
  found?: number
  texts?: number
  missing?: number
}

export interface OpenedXml {
  path: string
  name: string
  size: number
  parents: { tag: string; count: number }[]
}

export interface Preview {
  records: number
  lines: number
  sample: { tag: string; attributes: Record<string, string>; fields: { tag: string; text: string }[] }[]
}

/** One record tag and its fields; a file's selection is a list of these. */
export interface Group {
  parent: string
  targets: string[]
  contexts: string[]
}

export type FieldRole = 'translate' | 'context' | 'ignore'
export type FieldKind = 'text' | 'name' | 'id' | 'number' | 'flag' | 'path' | 'empty' | 'code'

export interface FieldPlan {
  tag: string
  kind: FieldKind
  count: number
  sample: string
  role: FieldRole
  technical: boolean
}

export interface TagPlan {
  tag: string
  records: number
  texts: number
  selected: boolean
  useful: boolean
  fields: FieldPlan[]
}

export interface Analysis {
  profile: { id: string; name: string }
  tags: TagPlan[]
}

export interface Preset {
  id: number
  label: string
  parent: string
  targets: string[]
  contexts: string[]
  file: string
}

export interface Progress {
  total: number
  translated: number
  confirmed: number
}

export interface ProjectSummary {
  id: string
  name: string
  folder: string
  gameRoot: string
  hasOriginals: boolean
  profile: string
  folderExists: boolean
  target: string
  lastFile: string
  updatedAt: number
  summary: { files: number; started: number; total: number; translated: number; confirmed: number }
}

/** What the engine found from a folder the user picked. */
export interface GameDetection {
  root: string
  xmlFolder: string
  name: string
  count: number
}

export interface ProjectFile {
  path: string
  name: string
  size: number
  groups: Group[]
  progress: Progress | null
}

export interface ProjectDetail extends ProjectSummary {
  files: ProjectFile[]
}

export interface Term {
  original: string
  translation: string
}

interface BridgeInfo {
  baseUrl: string
  token: string
}

export interface EngineStatus {
  phase: 'starting' | 'ready' | 'restarting' | 'failed' | 'stopped'
  reason: string
  attempts: number
  generation: number
  logPath: string
}

export async function retryEngine(): Promise<void> {
  if (isTauri()) await invoke('retry_engine')
  bridge = null
}

/** A refusal from the engine; `code` matches the `errors.*` messages. */
export class EngineError extends Error {
  code: string
  constructor(code: string) {
    super(code)
    this.code = code
  }
}

async function locateBridge(): Promise<BridgeInfo> {
  if (isTauri()) return invoke<BridgeInfo>('bridge_info')
  // Plain browser during development: point Vite at a running engine.
  const baseUrl = import.meta.env.VITE_BRIDGE_URL
  const token = import.meta.env.VITE_BRIDGE_TOKEN
  if (!baseUrl || !token) throw new Error('Set VITE_BRIDGE_URL and VITE_BRIDGE_TOKEN')
  return { baseUrl, token }
}

let bridge: BridgeInfo | null = null

export async function api<T = { ok: true }>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (!bridge) bridge = await locateBridge()
  let response: Response
  try {
    response = await fetch(bridge.baseUrl + path, {
      method,
      headers: { Authorization: `Bearer ${bridge.token}`, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      // A stalled snapshot must not stop polling and recovery indefinitely.
      signal: path === '/api/state' ? AbortSignal.timeout(8000) : undefined,
    })
  } catch {
    // The engine may have restarted on another port: look it up again next time.
    bridge = null
    throw new EngineError('offline')
  }
  if (response.status === 401) bridge = null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new EngineError(typeof data.error === 'string' ? data.error : 'unknown')
  return data as T
}

const IDLE_POLL_MS = 1200
const BUSY_POLL_MS = 350

/**
 * Polls the engine snapshot and keeps the entry list in sync, asking only for
 * the entries that changed since the last revision it holds.
 */
export function useEngine() {
  const [state, setState] = useState<EngineState | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [online, setOnline] = useState(true)
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null)
  const entriesRev = useRef(0)
  const stateRev = useRef(0)
  const busy = useRef(false)
  const running = useRef(false)
  const generation = useRef(0)

  const refresh = useCallback(async () => {
    if (running.current) return
    running.current = true
    try {
      if (isTauri()) {
        const status = await invoke<EngineStatus>('engine_status')
        setEngineStatus(status)
        if (status.generation !== generation.current) {
          generation.current = status.generation
          bridge = null
          stateRev.current = 0
          entriesRev.current = 0
          setState(null)
          setEntries([])
        }
        if (status.phase !== 'ready') throw new EngineError('offline')
      }
      const next = await api<EngineState>('/api/state')
      setOnline(true)
      busy.current = next.translating || next.xmlBusy || next.translatingEntries.length > 0
      if (stateRev.current === 0 || next.rev !== stateRev.current) {
        stateRev.current = next.rev
        setState(next)
      }
      if (!next.loaded) {
        entriesRev.current = 0
        setEntries((current) => (current.length ? [] : current))
      } else if (next.rev !== entriesRev.current) {
        const delta = await api<{ rev: number; full: boolean; entries: Entry[] }>(
          `/api/entries?since=${entriesRev.current}`,
        )
        entriesRev.current = delta.rev
        if (delta.full) {
          setEntries(delta.entries)
        } else if (delta.entries.length) {
          const changed = new Map(delta.entries.map((entry) => [entry.id, entry]))
          setEntries((current) => current.map((entry) => changed.get(entry.id) ?? entry))
        }
      }
    } catch {
      setOnline(false)
    } finally {
      running.current = false
    }
  }, [])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let stopped = false
    const tick = async () => {
      await refresh()
      if (!stopped) timer = setTimeout(tick, busy.current ? BUSY_POLL_MS : IDLE_POLL_MS)
    }
    tick()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [refresh])

  return { state, entries, online, engineStatus, refresh }
}
