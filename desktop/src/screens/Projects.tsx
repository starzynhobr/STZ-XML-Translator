import { AlertTriangle, Check, ChevronRight, CircleHelp, Download, FileText, Folder, FolderOpen, Languages, Play, Plus, RotateCcw, Search, SlidersHorizontal, Trash2, Upload } from 'lucide-react'
import StzLabsBadge from '@/components/StzLabsBadge'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import Select from '@/components/Select'
import { Button, IconButton, LogoMark, PageHeader, cardClass, cx, eyebrowClass, fieldClass, providerLabel } from '@/components/ui'
import { EngineError, api, setPendingSearch, type EngineState, type JobState, type GameDetection, type Progress, type ProjectDetail, type ProjectFile, type ProjectSummary, type SearchResult } from '@/lib/bridge'
import { PACKAGE_FILTER, formatSize, pickFile, pickFolder, pickSavePath } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'
import type { MessageKey } from '@/lib/messages'

/** The XML folder as seen from the game install, e.g. "MAA Redux_Data\StreamingAssets\XMLs". */
function insideGame(root: string, folder: string) {
  if (root && folder.toLowerCase().startsWith(root.toLowerCase())) return folder.slice(root.length).replace(/^[\\/]/, '') || '.'
  return folder
}

/** Where the game is and where its XMLs were found, with the action to pick another folder. */
function GameFolder({ root, folder, count, warn, busy, onPick }: { root: string; folder: string; count: number | null; warn: string | null; busy: boolean; onPick: () => void }) {
  const t = useT()
  return (
    <div className={cx(cardClass, 'flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5', warn && 'border-warn')}>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5 text-[13px]">
        {warn && <div className="flex items-center gap-2 text-sm font-semibold text-warn"><AlertTriangle aria-hidden="true" size={16} />{warn}</div>}
        <div className="flex min-w-0 items-center gap-2">
          <span className="w-[78px] shrink-0 text-dim">{t('gameFolder')}</span>
          <span className="truncate text-soft" title={root || folder}>{root || folder}</span>
        </div>
        {root && (
          <div className="flex min-w-0 items-center gap-2">
            <span className="w-[78px] shrink-0 text-dim">XMLs</span>
            <span className="truncate font-mono text-soft" title={folder}>{insideGame(root, folder)}</span>
            {count !== null && <span className="shrink-0 text-dim">· {t('projectFiles', { f: count })}</span>}
          </div>
        )}
      </div>
      <Button variant={warn ? 'primary' : 'secondary'} disabled={busy} onClick={onPick}>
        <FolderOpen aria-hidden="true" size={16} />
        {t('pickGameFolder')}
      </Button>
    </div>
  )
}

function targetLabel(state: EngineState, code: string) {
  return Object.entries(state.settings.targets).find(([, value]) => value === code)?.[0] ?? code
}

/** Translated share as a bar; confirmed work is the solid part. */
function ProgressBar({ progress, className }: { progress: Progress | null; className?: string }) {
  const total = progress?.total || 1
  const translated = progress ? (progress.translated / total) * 100 : 0
  const confirmed = progress ? (progress.confirmed / total) * 100 : 0
  return (
    <div aria-hidden="true" className={cx('relative h-1.5 overflow-hidden rounded-full bg-track', className)}>
      <div className="absolute inset-y-0 left-0 bg-warn-bar" style={{ width: `${translated}%` }} />
      <div className="absolute inset-y-0 left-0 bg-accent" style={{ width: `${confirmed}%` }} />
    </div>
  )
}

function percent(progress: Progress | null) {
  return progress && progress.total ? Math.round((progress.translated / progress.total) * 100) : 0
}

interface HomeProps {
  state: EngineState
  refresh: () => Promise<void>
  onOpenXml: () => void
  onOpenHelp: () => void
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

export function ProjectsHome({ state, refresh, onOpenXml, onOpenHelp, onOpenSettings, onOpenGlossary }: HomeProps) {
  const t = useT()
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [draft, setDraft] = useState<{ game: GameDetection | null; name: string; target: string } | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const fail = useCallback((error: unknown) => toast.error(errorText(t, error)), [t])

  const reload = useCallback(() => {
    void api<{ projects: ProjectSummary[] }>('/api/projects').then((data) => setProjects(data.projects), fail)
  }, [fail])

  useEffect(reload, [reload])

  const chooseFolder = async () => {
    const folder = await pickFolder()
    if (!folder) return
    try {
      const game = await api<GameDetection>('/api/projects/detect', 'POST', { path: folder })
      // Keep a name the user typed; otherwise suggest the game's own name.
      setDraft((current) => {
        const typed = current && current.name.trim() && current.name !== current.game?.name
        return { game, name: typed ? current.name : game.name, target: current?.target || state.settings.target }
      })
    } catch (error) {
      fail(error)
    }
  }

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
      await refresh()
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  const create = () =>
    run(async () => {
      if (!draft?.game) return
      const project = await api<ProjectSummary>('/api/projects', 'POST', { name: draft.name, folder: draft.game.xmlFolder, target: draft.target })
      await api(`/api/projects/${project.id}/open`, 'POST')
      setDraft(null)
    })

  const open = (project: ProjectSummary) => run(() => api(`/api/projects/${project.id}/open`, 'POST'))

  const remove = (project: ProjectSummary) =>
    run(async () => {
      await api(`/api/projects/${project.id}`, 'DELETE')
      setDeleting(null)
      reload()
    })

  return (
    <div className="flex min-h-full flex-col">
      <header className="relative flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <LogoMark />
        <span className="font-semibold tracking-[-0.01em]">XML Translator</span>
        <div className="absolute left-1/2 hidden -translate-x-1/2 md:block">
          <StzLabsBadge version={state.version} locale={state.settings.locale} />
        </div>
        <div className="flex-1" />
        <Button onClick={onOpenHelp}>
          <CircleHelp aria-hidden="true" size={16} />
          {t('helpTitle')}
        </Button>
        <Button onClick={onOpenGlossary}>{t('glossary')}</Button>
        <IconButton label={t('settings')} onClick={onOpenSettings}>
          <SlidersHorizontal aria-hidden="true" size={18} />
        </IconButton>
      </header>

      <main className="mx-auto flex w-full max-w-[960px] flex-col gap-6 px-5 py-9">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-0 flex-[1_1_320px]">
            <h1 className="m-0 mb-2 text-[32px] font-semibold leading-[1.15] tracking-[-0.03em]">{t('projectsTitle')}</h1>
            <p className="m-0 text-[15px] text-dim">{t('projectsSubtitle')}</p>
          </div>
          <Button onClick={onOpenXml} disabled={busy}>
            <FileText aria-hidden="true" size={16} />
            {t('openSingleXml')}
          </Button>
          <Button variant="primary" onClick={() => setDraft({ game: null, name: '', target: state.settings.target })} disabled={busy || draft !== null}>
            <Plus aria-hidden="true" size={16} />
            {t('newProject')}
          </Button>
        </div>

        {draft && (
          <form
            aria-label={t('newProject')}
            className={cx(cardClass, 'flex flex-col gap-4 p-5')}
            onSubmit={(event) => {
              event.preventDefault()
              void create()
            }}
          >
            <div className="flex flex-col gap-2">
              <span className="font-semibold">{t('step1GameFolder')}</span>
              <span className="text-[13px] text-dim">{t('gameFolderHint')}</span>
              {draft.game ? (
                <GameFolder
                  root={draft.game.root}
                  folder={draft.game.xmlFolder}
                  count={draft.game.count}
                  warn={draft.game.count ? null : t('noXmlFound')}
                  busy={busy}
                  onPick={() => void chooseFolder()}
                />
              ) : (
                <Button variant="primary" className="self-start" disabled={busy} onClick={() => void chooseFolder()}>
                  <FolderOpen aria-hidden="true" size={16} />
                  {t('pickGameFolder')}
                </Button>
              )}
            </div>
            {draft.game && draft.game.count > 0 && (
              <div className="flex flex-col gap-2">
                <label htmlFor="project-name" className="font-semibold">{t('step2ProjectName')}</label>
                <input
                  id="project-name"
                  value={draft.name}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  className={cx(fieldClass, 'min-w-0 max-w-[420px]')}
                />
              </div>
            )}
            {draft.game && draft.game.count > 0 && (
              <div className="flex flex-col gap-2">
                <label htmlFor="project-target" className="font-semibold">{t('step3Language')}</label>
                <Select
                  id="project-target"
                  className="max-w-[420px]"
                  value={draft.target}
                  onChange={(value) => setDraft({ ...draft, target: value })}
                  options={Object.entries(state.settings.targets).map(([label, value]) => ({ value, label }))}
                />
                <p className="m-0 text-[13px] text-dim">{t('newProjectHint', { language: targetLabel(state, draft.target) })}</p>
              </div>
            )}
            <div className="flex flex-wrap gap-2.5">
              <Button type="submit" variant="primary" disabled={busy || !draft.game?.count || !draft.name.trim()}>{t('createProject')}</Button>
              <Button onClick={() => setDraft(null)}>{t('cancel')}</Button>
            </div>
          </form>
        )}

        {projects === null || (draft && projects.length === 0) ? null : projects.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-[14px] border border-dashed border-edge px-6 py-14 text-center">
            <FolderOpen aria-hidden="true" size={36} strokeWidth={1.4} className="text-dim" />
            <h2 className="m-0 text-lg font-semibold">{t('noProjectsTitle')}</h2>
            <p className="m-0 max-w-[440px] text-dim">{t('noProjectsBody')}</p>
          </div>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
            {projects.map((project) => {
              const { summary } = project
              const progress = summary.started ? { total: summary.total, translated: summary.translated, confirmed: summary.confirmed } : null
              return (
                <li key={project.id} className={cx(cardClass, 'flex items-stretch overflow-hidden')}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void open(project)}
                    className="flex min-w-0 flex-1 flex-col gap-2.5 px-4 py-3.5 text-left enabled:hover:bg-raised"
                  >
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="text-[17px] font-semibold">{project.name}</span>
                      <span className="text-[13px] text-soft">{targetLabel(state, project.target)}</span>
                      <span className="flex-1" />
                      <span className="text-[13px] text-dim">
                        {progress ? t('projectProgress', { p: percent(progress), n: summary.started, f: summary.files }) : t('projectFiles', { f: summary.files })}
                      </span>
                    </div>
                    <ProgressBar progress={progress} />
                    <div className="flex items-center gap-2 text-[13px] text-dim">
                      {project.folderExists && summary.files ? <Folder aria-hidden="true" size={14} className="shrink-0" /> : <AlertTriangle aria-hidden="true" size={14} className="shrink-0 text-warn" />}
                      <span className="truncate" title={project.folder}>
                        {!project.folderExists ? t('folderMissing') : !summary.files ? t('noXmlFound') : project.gameRoot || project.folder}
                      </span>
                    </div>
                  </button>
                  <div className="flex items-center border-l border-line px-2">
                    {deleting === project.id ? (
                      <div className="flex flex-col gap-1.5 py-2">
                        <Button className="min-h-9 text-bad" disabled={busy} onClick={() => void remove(project)}>{t('confirmDelete')}</Button>
                        <Button className="min-h-9" onClick={() => setDeleting(null)}>{t('cancel')}</Button>
                      </div>
                    ) : (
                      <IconButton label={t('deleteProject', { name: project.name })} className="border-transparent" onClick={() => setDeleting(project.id)}>
                        <Trash2 aria-hidden="true" size={16} />
                      </IconButton>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        {projects && projects.length > 0 && <p className="m-0 text-[13px] text-dim">{t('deleteKeepsProgress')}</p>}
      </main>
    </div>
  )
}

/** Brings in translations someone made by editing the game's XMLs directly. */
function ImportPanel({ state, hasOriginals, busy, run, onApplied }: {
  state: EngineState
  hasOriginals: boolean
  busy: boolean
  run: (action: () => Promise<unknown>) => Promise<void>
  onApplied: () => void
}) {
  const t = useT()
  const job = state.import
  const start = async () => {
    const folder = await pickFolder()
    if (folder) await run(() => api('/api/import/start', 'POST', { path: folder }))
  }

  if (job.status === 'running') {
    const total = job.total || 1
    return (
      <div role="status" className={cx(cardClass, 'flex flex-col gap-2.5 px-4 py-3.5')}>
        <span className="text-sm font-semibold">{t('importComparing', { done: job.done ?? 0, total: job.total ?? 0 })}</span>
        <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-track">
          <div className="h-full bg-accent transition-[width]" style={{ width: `${((job.done ?? 0) / total) * 100}%` }} />
        </div>
      </div>
    )
  }

  if (job.status === 'ready') {
    const files = (job.files ?? []).filter((file) => file.found > 0)
    return (
      <div className={cx(cardClass, 'flex flex-col gap-3 border-accent px-4 py-4')}>
        <div className="font-semibold">
          {job.found ? t('importFound', { n: job.found, f: files.length }) : t('importNothing')}
        </div>
        {files.length > 0 && (
          <ul className="m-0 max-h-[220px] list-none overflow-y-auto p-0 text-[13px]">
            {files.map((file) => (
              <li key={file.file} className="flex justify-between gap-4 py-1">
                <span className="truncate font-mono">{file.file}</span>
                <span className="shrink-0 text-dim">{t('fileProgress', { t: file.found, n: file.texts })}</span>
              </li>
            ))}
          </ul>
        )}
        {(job.missing ?? 0) > 0 && <p className="m-0 text-[13px] text-dim">{t('importMissing', { n: job.missing ?? 0 })}</p>}
        <p className="m-0 flex gap-2 text-[13px] text-warn">
          <AlertTriangle aria-hidden="true" size={15} className="mt-0.5 shrink-0" />
          {t('importReviewNote')}
        </p>
        <div className="flex flex-wrap gap-2.5">
          <Button variant="primary" disabled={busy || !job.found} onClick={() => void run(async () => { await api('/api/import/apply', 'POST'); onApplied() })}>
            {t('importApply', { n: job.found ?? 0 })}
          </Button>
          <Button disabled={busy} onClick={() => void run(() => api('/api/import/cancel', 'POST'))}>{t('cancel')}</Button>
        </div>
      </div>
    )
  }

  if (hasOriginals) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-dim">
        <Check aria-hidden="true" size={15} className="text-accent" />
        <span>{t('originalsKept')}</span>
        <button type="button" disabled={busy} onClick={() => void start()} className="text-soft underline-offset-2 hover:text-ink hover:underline">
          {t('importAgain')}
        </button>
      </div>
    )
  }

  return (
    <div className={cx(cardClass, 'flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5')}>
      <div className="min-w-0 flex-[1_1_320px]">
        <div className="text-sm font-semibold">{t('importTitle')}</div>
        <div className="text-[13px] text-dim">{job.status === 'error' ? t('importFailed') : t('importBody')}</div>
      </div>
      <Button disabled={busy} onClick={() => void start()}>
        <Download aria-hidden="true" size={16} />
        {t('importButton')}
      </Button>
    </div>
  )
}

const JOB_RUNNING: Record<NonNullable<JobState['kind']>, MessageKey> = {
  apply: 'jobApplying',
  play: 'jobApplying',
  restore: 'jobRestoring',
  export: 'jobExporting',
  translate: 'jobTranslating',
  update: 'jobComparing',
}

/** Progress and outcome of the project's long operation. */
function JobPanel({ job, busy, run, onFinished }: {
  job: JobState
  busy: boolean
  run: (action: () => Promise<unknown>) => Promise<void>
  onFinished: () => void
}) {
  const t = useT()
  if (job.status === 'idle' || !job.kind) return null
  const result = (job.result ?? {}) as Record<string, number>
  const dismiss = () => void run(async () => { await api('/api/job/dismiss', 'POST'); onFinished() })

  if (job.status === 'running') {
    const total = job.total || 1
    return (
      <div role="status" className={cx(cardClass, 'flex flex-col gap-2.5 px-4 py-3.5')}>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold">
            {job.cancelling ? t('jobCancelling') : t(JOB_RUNNING[job.kind], { done: job.done ?? 0, total: job.total ?? 0 })}
          </span>
          {job.file && !job.cancelling && <span className="truncate font-mono text-xs text-dim">{job.file}</span>}
          <span className="flex-1" />
          {job.kind === 'translate' && (
            <Button className="min-h-9" disabled={job.cancelling} onClick={() => void run(() => api('/api/job/cancel', 'POST'))}>
              {job.cancelling ? t('cancellingShort') : t('cancel')}
            </Button>
          )}
        </div>
        {job.cancelling && <p className="m-0 text-[13px] text-dim">{t('jobCancellingNote')}</p>}
        <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-track">
          <div className="h-full bg-accent transition-[width]" style={{ width: `${((job.done ?? 0) / total) * 100}%` }} />
        </div>
      </div>
    )
  }

  if (job.status === 'error') {
    return (
      <div role="alert" className={cx(cardClass, 'flex flex-wrap items-center gap-3 border-warn px-4 py-3.5')}>
        <AlertTriangle aria-hidden="true" size={16} className="text-warn" />
        <span className="min-w-0 flex-1 text-sm">{errorText(t, new EngineError(job.error || 'unknown'))}</span>
        <Button className="min-h-9" onClick={dismiss}>{t('ok')}</Button>
      </div>
    )
  }

  if (job.kind === 'update' && job.status === 'done') {
    const files = (job.result?.files ?? []) as { file: string; changed: number; moved: number; removed: number }[]
    return (
      <div className={cx(cardClass, 'flex flex-col gap-3 border-accent px-4 py-4')}>
        <div className="font-semibold">{t('updateSummary', { kept: result.kept ?? 0, changed: result.changed ?? 0, moved: result.moved ?? 0, added: result.new ?? 0 })}</div>
        {files.length > 0 && (
          <ul className="m-0 max-h-[200px] list-none overflow-y-auto p-0 text-[13px]">
            {files.map((file) => (
              <li key={file.file} className="flex justify-between gap-4 py-1">
                <span className="truncate font-mono">{file.file}</span>
                <span className="shrink-0 text-dim">{t('updateFileLine', { changed: file.changed, moved: file.moved, removed: file.removed })}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="m-0 text-[13px] text-dim">{t('updateNote')}</p>
        <div className="flex flex-wrap gap-2.5">
          <Button variant="primary" disabled={busy} onClick={() => void run(async () => { await api('/api/project/update/apply', 'POST'); onFinished() })}>{t('updateApply')}</Button>
          <Button disabled={busy} onClick={dismiss}>{t('cancel')}</Button>
        </div>
      </div>
    )
  }

  const done: Record<string, string> = {
    apply: t('jobApplied', { f: result.files ?? 0, n: result.texts ?? 0 }),
    play: t('jobApplied', { f: result.files ?? 0, n: result.texts ?? 0 }),
    restore: t('jobRestored', { f: result.files ?? 0 }),
    export: t('jobExported', { f: result.files ?? 0, n: result.texts ?? 0 }),
    translate: t('jobTranslated', { f: result.files ?? 0, n: result.texts ?? 0 }),
    update: '',
  }
  return (
    <div role="status" className={cx(cardClass, 'flex flex-wrap items-center gap-3 px-4 py-3.5')}>
      <Check aria-hidden="true" size={16} className="text-accent" />
      <span className="min-w-0 flex-1 text-sm">{job.status === 'cancelled' ? t('jobCancelled') : done[job.kind]}</span>
      <Button className="min-h-9" onClick={dismiss}>{t('ok')}</Button>
    </div>
  )
}

/** Translate the whole game, put it in the game, and the version/sharing tools. */
function GameActions({ state, detail, busy, run }: {
  state: EngineState
  detail: ProjectDetail
  busy: boolean
  run: (action: () => Promise<unknown>) => Promise<void>
}) {
  const t = useT()
  const working = busy || state.job.status === 'running' || state.import.status === 'running'
  const { summary } = detail
  // Translating everything spends quota for a long while: say what will happen first.
  const [confirming, setConfirming] = useState(false)
  const engine = state.settings.provider === 'Gemini' ? `Gemini · ${state.settings.model.replace(/^Gemini\s+/, '')}` : providerLabel(state.settings.provider, t)
  const play = useCallback(() => {
    if (!working && detail.gameExe) void run(() => api('/api/game/apply', 'POST', { launch: true }))
  }, [working, detail.gameExe, run])

  // F5: apply and start the game, like a test run in an editor (and never a page reload).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'F5') return
      event.preventDefault()
      play()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [play])

  const pickAndRun = async (endpoint: string, picker: () => Promise<string | null>) => {
    const path = await picker()
    if (path) await run(() => api(endpoint, 'POST', { path }))
  }
  const exportPackage = async () => {
    const path = await pickSavePath(`${detail.name}-${state.settings.target}.stzpack`, PACKAGE_FILTER)
    if (!path) return
    await run(async () => {
      const result = await api<{ files: number; texts: number }>('/api/project/package/export', 'POST', { path })
      toast.success(t('packageExported', { n: result.texts }))
    })
  }
  const importPackage = async () => {
    const path = await pickFile(PACKAGE_FILTER)
    if (!path) return
    await run(async () => {
      const result = await api<{ imported: number; conflicts: number; glossaryAdded: number }>('/api/project/package/import', 'POST', { path })
      toast.success(t('packageImported', { n: result.imported, c: result.conflicts, g: result.glossaryAdded }))
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className={cx(cardClass, 'flex flex-wrap items-center gap-2.5 px-4 py-3.5')}>
        <div className="min-w-0 flex-[1_1_240px]">
          <div className="text-sm font-semibold">{t('gameActionsTitle')}</div>
          <div className="text-[13px] text-dim">
            {detail.applied ? t('gameApplied') : t('gameActionsBody', { n: summary.translated })}
          </div>
        </div>
        <Button variant="primary" disabled={working || confirming} onClick={() => setConfirming(true)}>
          <Languages aria-hidden="true" size={16} />
          {t('translateProject')}
        </Button>
        <Button disabled={working || !summary.translated} onClick={() => void run(() => api('/api/game/apply', 'POST', {}))}>
          <Upload aria-hidden="true" size={16} />
          {t('applyToGame')}
        </Button>
        {detail.gameExe && (
          <Button disabled={working || !summary.translated} onClick={play} title={detail.gameExe}>
            <Play aria-hidden="true" size={16} />
            {t('applyAndPlay')}
            <span className="rounded-[5px] bg-black/15 px-1.5 py-0.5 font-mono text-[11px]">F5</span>
          </Button>
        )}
        {detail.applied && (
          <Button disabled={working} onClick={() => void run(() => api('/api/game/restore', 'POST'))}>
            <RotateCcw aria-hidden="true" size={16} />
            {t('restoreGame')}
          </Button>
        )}
      </div>
      {confirming && (
        <div role="dialog" aria-label={t('confirmTranslateTitle')} className={cx(cardClass, 'flex flex-col gap-3 border-accent px-4 py-4')}>
          <div className="font-semibold">{t('confirmTranslateTitle')}</div>
          <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-soft">
            <li>{t('confirmTranslateFiles', { f: summary.files, s: summary.started })}</li>
            <li>{t('confirmTranslateEngine', { engine })}</li>
            <li>{t('confirmTranslateResume')}</li>
          </ul>
          <p className="m-0 flex gap-2 text-[13px] text-warn">
            <AlertTriangle aria-hidden="true" size={15} className="mt-0.5 shrink-0" />
            {t('confirmTranslateQuota')}
          </p>
          <div className="flex flex-wrap gap-2.5">
            <Button variant="primary" disabled={working} onClick={() => { setConfirming(false); void run(() => api('/api/project/translate', 'POST')) }}>
              {t('confirmTranslateStart')}
            </Button>
            <Button onClick={() => setConfirming(false)}>{t('cancel')}</Button>
          </div>
        </div>
      )}
      <details className="group text-[13px]">
        <summary className="cursor-pointer select-none text-soft hover:text-ink">{t('moreTools')}</summary>
        <div className="mt-2.5 flex flex-wrap gap-2">
          <Button className="min-h-9 text-[13px]" disabled={working} onClick={() => void pickAndRun('/api/project/update', pickFolder)}>{t('newGameVersion')}</Button>
          <Button className="min-h-9 text-[13px]" disabled={working || !summary.translated} onClick={() => void pickAndRun('/api/project/export-xmls', pickFolder)}>{t('exportXmls')}</Button>
          <Button className="min-h-9 text-[13px]" disabled={working || !summary.translated} onClick={() => void exportPackage()}>{t('exportPackage')}</Button>
          <Button className="min-h-9 text-[13px]" disabled={working} onClick={() => void importPackage()}>{t('importPackage')}</Button>
        </div>
      </details>
    </div>
  )
}

interface ViewProps {
  state: EngineState
  refresh: () => Promise<void>
  onPickFile: (path: string) => void
  onOpenHelp: () => void
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

export function ProjectView({ state, refresh, onPickFile, onOpenHelp, onOpenSettings, onOpenGlossary }: ViewProps) {
  const t = useT()
  const id = state.project?.id ?? ''
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)

  const fail = useCallback((error: unknown) => toast.error(errorText(t, error)), [t])

  const reload = useCallback(() => {
    if (id) void api<ProjectDetail>(`/api/projects/${id}`).then(setDetail, fail)
  }, [id, fail])

  // Progress changes while a file is open or a whole-project job runs: refetch when either ends.
  useEffect(reload, [reload, state.settings.target, state.job.status])

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
      await refresh()
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  const openFile = (file: ProjectFile) => {
    if (!file.groups.length) {
      onPickFile(file.path)
      return
    }
    void run(async () => {
      await api('/api/xml/open', 'POST', { path: file.path })
      await api('/api/xml/load', 'POST', { groups: file.groups })
    })
  }

  const relocate = async () => {
    const folder = await pickFolder()
    if (folder) await run(async () => {
      await api(`/api/projects/${id}`, 'PUT', { folder })
      reload()
    })
  }

  const files = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const all = detail?.files ?? []
    return needle ? all.filter((file) => file.name.toLowerCase().includes(needle)) : all
  }, [detail, query])

  // Texts across every opened file, from the engine's database.
  const [hits, setHits] = useState<SearchResult[]>([])
  useEffect(() => {
    const needle = query.trim()
    if (needle.length < 3) {
      setHits([])
      return
    }
    let stale = false
    const timer = setTimeout(() => {
      api<{ results: SearchResult[] }>(`/api/search?q=${encodeURIComponent(needle)}`).then(
        (data) => !stale && setHits(data.results),
        () => !stale && setHits([]),
      )
    }, 250)
    return () => {
      stale = true
      clearTimeout(timer)
    }
  }, [query])

  const openHit = (hit: SearchResult) => {
    const file = detail?.files.find((item) => item.name === hit.file)
    if (!file) return
    setPendingSearch(hit.original)
    openFile(file)
  }

  const last = detail?.files.find((file) => file.name === detail.lastFile && file.groups.length)

  return (
    <div className="flex min-h-full flex-col">
      <PageHeader title={state.project?.name ?? ''} backLabel={t('projectsTitle')} onBack={() => void run(() => api('/api/projects/close', 'POST'))}>
        <span className="flex items-center gap-2 text-[13px] text-dim">
          {t('to')}
          <Select
            aria-label={t('to')}
            className="w-[190px] max-w-full text-sm"
            value={state.settings.target}
            onChange={(value) => void run(() => api('/api/settings', 'PUT', { target: value }))}
            options={Object.entries(state.settings.targets).map(([label, value]) => ({ value, label }))}
          />
        </span>
        <Button onClick={onOpenHelp}>
          <CircleHelp aria-hidden="true" size={16} />
          {t('helpTitle')}
        </Button>
        <Button onClick={onOpenGlossary}>{t('glossary')}</Button>
        <IconButton label={t('settings')} onClick={onOpenSettings}>
          <SlidersHorizontal aria-hidden="true" size={18} />
        </IconButton>
      </PageHeader>

      <main className="mx-auto flex w-full max-w-[960px] flex-col gap-5 px-5 py-7">
        {detail && (
          <GameFolder
            root={detail.gameRoot}
            folder={detail.folder}
            count={detail.folderExists ? detail.files.length : null}
            warn={!detail.folderExists ? t('folderMissing') : detail.files.length === 0 ? t('noXmlFound') : null}
            busy={busy}
            onPick={() => void relocate()}
          />
        )}
        {detail && !detail.folderExists && <p className="m-0 text-dim">{t('folderMissingBody')}</p>}
        {detail && detail.folderExists && detail.files.length > 0 && (
          <ImportPanel state={state} hasOriginals={detail.hasOriginals} busy={busy} run={run} onApplied={reload} />
        )}
        {detail && detail.folderExists && detail.files.length > 0 && (
          <>
            <JobPanel job={state.job} busy={busy} run={run} onFinished={reload} />
            <GameActions state={state} detail={detail} busy={busy} run={run} />
          </>
        )}
        {detail && detail.folderExists && detail.files.length > 0 && (
          <>
            {last && (
              <Button variant="primary" className="self-start" disabled={busy} onClick={() => openFile(last)}>
                {t('continueFile', { name: last.name })}
                <ChevronRight aria-hidden="true" size={16} />
              </Button>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <span className={eyebrowClass}>{t('projectFiles', { f: detail.summary.files })}</span>
              <span className="text-[13px] text-dim">
                {detail.summary.started ? t('projectStarted', { n: detail.summary.started, t: detail.summary.translated, c: detail.summary.confirmed }) : t('projectNotStarted')}
              </span>
              <span className="flex-1" />
              <label className="relative flex min-w-[220px] flex-[0_1_300px] items-center">
                <Search aria-hidden="true" size={16} className="pointer-events-none absolute left-3 text-dim" />
                <input aria-label={t('searchFiles')} placeholder={t('searchFiles')} value={query} onChange={(event) => setQuery(event.target.value)} className={cx(fieldClass, 'w-full pl-9')} />
              </label>
            </div>

            {hits.length > 0 && (
              <section aria-label={t('textHits', { n: hits.length })} className="flex flex-col gap-2">
                <span className={eyebrowClass}>{t('textHits', { n: hits.length })}</span>
                <ul className={cx(cardClass, 'm-0 max-h-[320px] list-none divide-y divide-line overflow-y-auto p-0')}>
                  {hits.map((hit) => (
                    <li key={`${hit.file}${hit.xpath}`}>
                      <button type="button" disabled={busy} onClick={() => openHit(hit)} className="grid w-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-4 gap-y-0.5 px-4 py-2.5 text-left text-[13px] enabled:hover:bg-raised">
                        <span className="col-span-2 font-mono text-xs text-dim">{hit.file}</span>
                        <span className="truncate text-ink" title={hit.original}>{hit.original}</span>
                        <span className={cx('truncate', hit.translation ? 'text-soft' : 'text-faint')} title={hit.translation}>{hit.translation || t('noTranslation')}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {(
              <ul className={cx(cardClass, 'm-0 list-none divide-y divide-line overflow-hidden p-0')}>
                {files.map((file) => (
                  <li key={file.path}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => openFile(file)}
                      className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-3 text-left enabled:hover:bg-raised sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_160px]"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-mono text-sm">{file.name}</span>
                        <span className="block text-xs text-dim">{formatSize(file.size)}</span>
                      </span>
                      <span className="hidden min-w-0 truncate font-mono text-xs text-dim sm:block">
                        {file.groups.length ? file.groups.map((group) => group.parent).join(', ') : t('notConfigured')}
                      </span>
                      <span className="flex flex-col items-end gap-1.5">
                        <span className="text-xs text-dim">
                          {file.progress ? t('fileProgress', { t: file.progress.translated, n: file.progress.total }) : '—'}
                        </span>
                        <ProgressBar progress={file.progress} className="w-full max-w-[160px]" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
    </div>
  )
}
