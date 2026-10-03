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
  context: Record<string, string>
  error: string
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
  structure: { parent: string; targets: string[]; contexts: string[] } | null
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

export interface Preset {
  id: number
  label: string
  parent: string
  targets: string[]
  contexts: string[]
  file: string
}

export interface Term {
  original: string
  translation: string
}

interface BridgeInfo {
  baseUrl: string
  token: string
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
  const entriesRev = useRef(0)
  const stateRev = useRef(0)
  const busy = useRef(false)
  const running = useRef(false)

  const refresh = useCallback(async () => {
    if (running.current) return
    running.current = true
    try {
      const next = await api<EngineState>('/api/state')
      setOnline(true)
      busy.current = next.translating || next.xmlBusy || next.translatingEntries.length > 0
      if (next.rev !== stateRev.current) {
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

  return { state, entries, online, refresh }
}
