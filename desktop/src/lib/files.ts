import { invoke, isTauri } from '@tauri-apps/api/core'

interface Filter {
  name: string
  extensions: string[]
}

/** Native dialogs in the desktop shell; a typed path in a plain dev browser. */
export async function pickFile(filters: Filter[]): Promise<string | null> {
  if (isTauri()) {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const chosen = await open({ multiple: false, directory: false, filters })
    return typeof chosen === 'string' ? chosen : null
  }
  return window.prompt('Path of the file to open') || null
}

export async function pickFolder(): Promise<string | null> {
  if (isTauri()) {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const chosen = await open({ multiple: false, directory: true })
    return typeof chosen === 'string' ? chosen : null
  }
  return window.prompt('Path of the folder to open') || null
}

export async function pickSavePath(defaultPath: string, filters: Filter[]): Promise<string | null> {
  if (isTauri()) {
    const { save } = await import('@tauri-apps/plugin-dialog')
    return (await save({ defaultPath, filters })) || null
  }
  return window.prompt('Path to save to', defaultPath) || null
}

export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    const { openUrl } = await import('@tauri-apps/plugin-opener')
    await openUrl(url)
  } else {
    window.open(url, '_blank', 'noopener')
  }
}

export async function quitApp(): Promise<void> {
  if (isTauri()) await invoke('quit')
}

export const XML_FILTER: Filter[] = [{ name: 'XML', extensions: ['xml'] }]
export const JSON_FILTER: Filter[] = [{ name: 'JSON', extensions: ['json'] }]
export const CSV_FILTER: Filter[] = [{ name: 'CSV', extensions: ['csv'] }]
export const BACKUP_FILTER: Filter[] = [{ name: 'JSON / CSV', extensions: ['json', 'csv'] }]
export const PACKAGE_FILTER: Filter[] = [{ name: 'STZ', extensions: ['stzpack'] }]

export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
