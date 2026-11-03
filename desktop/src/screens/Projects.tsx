import { AlertTriangle, ChevronRight, FileText, Folder, FolderOpen, Plus, Search, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import Select from '@/components/Select'
import { Button, IconButton, LogoMark, PageHeader, cardClass, cx, eyebrowClass, fieldClass } from '@/components/ui'
import { api, type EngineState, type GameDetection, type Progress, type ProjectDetail, type ProjectFile, type ProjectSummary } from '@/lib/bridge'
import { formatSize, pickFolder } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'

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
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

export function ProjectsHome({ state, refresh, onOpenXml, onOpenSettings, onOpenGlossary }: HomeProps) {
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
      <header className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <LogoMark />
        <span className="font-semibold tracking-[-0.01em]">XML Translator</span>
        <div className="flex-1" />
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

interface ViewProps {
  state: EngineState
  refresh: () => Promise<void>
  onPickFile: (path: string) => void
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

export function ProjectView({ state, refresh, onPickFile, onOpenSettings, onOpenGlossary }: ViewProps) {
  const t = useT()
  const id = state.project?.id ?? ''
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)

  const fail = useCallback((error: unknown) => toast.error(errorText(t, error)), [t])

  const reload = useCallback(() => {
    if (id) void api<ProjectDetail>(`/api/projects/${id}`).then(setDetail, fail)
  }, [id, fail])

  // Progress changes while a file is open; refetch whenever the project comes back.
  useEffect(reload, [reload, state.settings.target])

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
