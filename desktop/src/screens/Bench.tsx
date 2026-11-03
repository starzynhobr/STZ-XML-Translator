import Select from '@/components/Select'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronDown, ChevronUp, FileText, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button, IconButton, LogoMark, buttonClass, cardClass, cx, eyebrowClass, fieldClass, providerLabel } from '@/components/ui'
import { api, takePendingSearch, type EngineState, type Entry, type Status, type Suggestion, type Term, type Version } from '@/lib/bridge'
import { XML_FILTER, pickSavePath } from '@/lib/files'
import { errorText, useT, type Translate } from '@/lib/i18n'
import type { MessageKey } from '@/lib/messages'

type Filter = 'all' | 'pending' | 'review' | 'confirmed' | 'errors'

const FILTER_STATUS: Record<Exclude<Filter, 'all'>, Status[]> = {
  pending: ['pending', 'translating'],
  review: ['translated'],
  confirmed: ['confirmed'],
  errors: ['error'],
}

const STATUS_LABEL: Record<Status, MessageKey> = {
  pending: 'statusPending',
  translating: 'statusTranslating',
  translated: 'statusTranslated',
  confirmed: 'statusConfirmed',
  error: 'statusError',
}

const ROW_HEIGHT = 68
const GRID = 'grid grid-cols-[44px_150px_minmax(0,1fr)_minmax(0,1fr)_128px] gap-4'

/** State is never colour alone: each one has its own mark and a text label. */
function StatusMark({ status, t }: { status: Status; t: Translate }) {
  const tone = {
    pending: 'text-dim',
    translating: 'text-soft',
    translated: 'text-warn',
    confirmed: 'text-ink',
    error: 'text-bad',
  }[status]
  return (
    <span className={cx('flex items-center gap-2 self-start text-[13px]', tone)}>
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" className={status === 'translating' ? 'pulse-dot' : undefined}>
        {status === 'confirmed' ? (
          <>
            <circle cx="8" cy="8" r="6.25" className="fill-accent stroke-accent" strokeWidth="1.5" />
            <path d="M5 8.2l2 2 4-4.4" className="stroke-on-accent" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : status === 'error' ? (
          <>
            <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" />
            <path d="M8 4.8v3.8M8 11v.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </>
        ) : status === 'translating' ? (
          <circle cx="8" cy="8" r="3.5" fill="currentColor" />
        ) : (
          <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" className={status === 'pending' ? 'opacity-60' : undefined} />
        )}
      </svg>
      {t(STATUS_LABEL[status])}
    </span>
  )
}

const SOURCE_LABEL: Record<string, MessageKey> = {
  ai: 'sourceAi',
  manual: 'sourceManual',
  confirm: 'sourceConfirm',
  import: 'sourceImport',
  memory: 'sourceMemory',
  agent: 'sourceAgent',
  edit: 'sourceEdit',
  reset: 'sourceEdit',
}

/** How the same original was translated elsewhere in the game (translation memory). */
function Suggestions({ entry, onUse }: { entry: Entry; onUse: (text: string) => void }) {
  const t = useT()
  const [items, setItems] = useState<Suggestion[]>([])
  useEffect(() => {
    let stale = false
    api<{ suggestions: Suggestion[] }>(`/api/entries/suggestions?id=${encodeURIComponent(entry.id)}`).then(
      (data) => !stale && setItems(data.suggestions),
      () => !stale && setItems([]),
    )
    return () => {
      stale = true
    }
  }, [entry.id, entry.translation])
  if (!items.length) return null
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-dim">{t('memoryTitle')}</span>
      {items.map((item) => (
        <button
          key={item.translation}
          type="button"
          onClick={() => onUse(item.translation)}
          className="flex items-baseline gap-2 rounded-[10px] border border-edge px-3 py-2 text-left text-[13px] hover:bg-raised"
        >
          <span className="min-w-0 flex-1 text-ink">{item.translation}</span>
          <span className="shrink-0 text-xs text-dim">
            {item.confirmed ? t('memoryConfirmed', { n: item.uses }) : t('memoryUses', { n: item.uses })}
          </span>
        </button>
      ))}
    </div>
  )
}

/** Earlier versions of the selected entry, from the engine's SQLite history. */
function History({ entry, onRestore }: { entry: Entry; onRestore: (text: string) => void }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<Version[]>([])

  // Refetch when the entry or its saved text changes.
  useEffect(() => {
    let stale = false
    api<{ versions: Version[] }>(`/api/entries/history?id=${encodeURIComponent(entry.id)}`).then(
      (data) => !stale && setVersions(data.versions),
      () => !stale && setVersions([]),
    )
    return () => {
      stale = true
    }
  }, [entry.id, entry.translation, entry.status])

  if (!versions.length) return null
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex items-center gap-1.5 self-start text-[13px] text-soft hover:text-ink">
        {open ? <ChevronUp aria-hidden="true" size={14} /> : <ChevronDown aria-hidden="true" size={14} />}
        {t('historyTitle', { n: versions.length })}
      </button>
      {open && (
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {versions.map((version, index) => (
            <li key={index} className="flex flex-col gap-1 rounded-[10px] border border-line px-3 py-2">
              <div className="flex items-center gap-2 text-xs text-dim">
                <span className="font-medium text-soft">{t(SOURCE_LABEL[version.source] ?? 'sourceEdit')}</span>
                <span>{new Date(version.at * 1000).toLocaleString(document.documentElement.lang || undefined)}</span>
                <span className="flex-1" />
                {index > 0 && version.newText && version.newText !== entry.translation && (
                  <button type="button" className="text-soft underline-offset-2 hover:text-ink hover:underline" onClick={() => onRestore(version.newText)}>
                    {t('restoreVersion')}
                  </button>
                )}
              </div>
              <div className="text-[13px] text-ink">{version.newText || <span className="text-dim">—</span>}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

const fieldKey = (entry: Entry) => (entry.group ? `${entry.group} › ${entry.sourceTag}` : entry.sourceTag)

const contextOf = (entry: Entry) => Object.values(entry.context).find(Boolean) || entry.sourceTag

interface Props {
  state: EngineState
  entries: Entry[]
  terms: Term[]
  refresh: () => Promise<void>
  onOpenStart: () => void
  onOpenSettings: () => void
  onOpenGlossary: () => void
  onOpenUpdate: () => void
}

export default function Bench({ state, entries, terms, refresh, onOpenStart, onOpenSettings, onOpenGlossary, onOpenUpdate }: Props) {
  const t = useT()
  const [filter, setFilter] = useState<Filter>('all')
  // A project-wide search result opens its file already filtered to that text.
  const [query, setQuery] = useState(takePendingSearch)
  const [field, setField] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const editing = useRef(false)
  const scroller = useRef<HTMLDivElement>(null)

  const { counts, settings, structure } = state
  const hasContext = Boolean(structure?.contexts.length)

  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
      await refresh()
    } catch (error) {
      toast.error(errorText(t, error))
    }
  }

  const visible = useMemo(() => {
    const wanted = filter === 'all' ? null : FILTER_STATUS[filter]
    const needle = query.trim().toLowerCase()
    return entries.filter((entry) => {
      if (wanted && !wanted.includes(entry.status)) return false
      if (field && fieldKey(entry) !== field) return false
      if (!needle) return true
      return [entry.original, entry.translation, entry.sourceTag, ...Object.values(entry.context)].some((value) =>
        value.toLowerCase().includes(needle),
      )
    })
  }, [entries, filter, query, field])

  // Tag › field pairs with their counts, in the order they first appear.
  const fields = useMemo(() => {
    const counts = new Map<string, number>()
    for (const entry of entries) counts.set(fieldKey(entry), (counts.get(fieldKey(entry)) ?? 0) + 1)
    return [...counts]
  }, [entries])
  const fieldOptions = [
    { value: '', label: t('allFields', { n: entries.length }) },
    ...fields.map(([key, n]) => ({ value: key, label: `${key} · ${n}` })),
  ]

  const selected = useMemo(() => entries.find((entry) => entry.id === selectedId) ?? null, [entries, selectedId])

  // Keep something selected: the inspector is where the work happens.
  useEffect(() => {
    if (!selected && visible.length) setSelectedId(visible[0].id)
  }, [selected, visible])

  // A new filter, search or field shows its own first entry instead of one it hides.
  // Only then: an entry that leaves the list after an edit stays in front of the user.
  const shownIds = useRef(new Set<string>())
  shownIds.current = new Set(visible.map((entry) => entry.id))
  useEffect(() => {
    if (selectedId && !shownIds.current.has(selectedId) && visible.length) {
      setSelectedId(visible[0].id)
      scroller.current?.scrollTo({ top: 0 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, query, field])

  // The engine owns the text; mirror it unless the user is mid-edit.
  useEffect(() => {
    if (!editing.current) setDraft(selected?.translation ?? '')
  }, [selected?.id, selected?.translation])

  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  const select = (id: string) => {
    commitDraft()
    editing.current = false
    setSelectedId(id)
  }

  const move = (step: number) => {
    const at = visible.findIndex((entry) => entry.id === selectedId)
    const next = visible[Math.min(visible.length - 1, Math.max(0, at + step))]
    if (!next || next.id === selectedId) return
    select(next.id)
    virtualizer.scrollToIndex(visible.indexOf(next), { align: 'auto' })
  }

  const commitDraft = () => {
    if (!selected || draft === selected.translation || selected.status === 'translating') return
    const id = selected.id
    void run(() => api('/api/entries/edit', 'POST', { id, text: draft }))
  }

  const confirm = () => {
    if (!selected) return
    const id = selected.id
    editing.current = false
    void run(async () => {
      await api('/api/entries/confirm', 'POST', { id, text: draft })
      move(1)
    })
  }

  const exportXml = async () => {
    const path = await pickSavePath(state.file?.path ?? 'translated.xml', XML_FILTER)
    if (!path) return
    await run(async () => {
      await api('/api/xml/export', 'POST', { path })
      toast.success(t('toastExported'))
    })
  }

  const toTranslate = counts.pending + counts.error
  const total = state.total || 1
  const filters: [Filter, MessageKey, number][] = [
    ['all', 'filterAll', state.total],
    ['pending', 'filterPending', counts.pending + counts.translating],
    ['review', 'filterReview', counts.translated],
    ['confirmed', 'filterConfirmed', counts.confirmed],
  ]
  if (counts.error > 0 || filter === 'errors') filters.push(['errors', 'filterErrors', counts.error])

  const matches = useMemo(() => {
    if (!selected) return []
    const text = selected.original.toLowerCase()
    return terms.filter((term) => text.includes(term.original.toLowerCase()))
  }, [selected, terms])

  const selectedBusy = selected?.status === 'translating'

  return (
    <div className="flex min-h-full flex-col lg:h-full">
      {/* One row from tablet width up: the file and tag chips give way first. */}
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3 md:flex-nowrap">
        <IconButton label={state.project ? t('backToProject', { name: state.project.name }) : t('backToProjects')} disabled={state.translating} onClick={() => void run(() => api('/api/xml/close', 'POST'))}>
          <LogoMark className="size-[22px]" />
        </IconButton>
        {state.project && <span className="hidden max-w-[160px] shrink-0 truncate text-sm font-semibold 2xl:block" title={state.project.folder}>{state.project.name}</span>}
        <Button variant="chip" onClick={onOpenStart} title={t('changeFile')} className="min-w-0 shrink">
          <FileText aria-hidden="true" size={16} className="shrink-0" />
          <span className="max-w-[220px] truncate">{state.file?.name}</span>
        </Button>
        {structure && (
          <Button variant="chip" onClick={onOpenStart} title={t('editStructure')} className="min-w-0 shrink-[2] text-[13px]">
            {structure.groups.length > 1 ? (
              <span className="max-w-[320px] truncate font-mono" title={structure.groups.map((g) => `${g.parent} › ${g.targets.join(', ')}`).join('\n')}>
                {structure.groups.map((g) => g.parent).join(', ')}
              </span>
            ) : (
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate font-mono">
                  {structure.parent} › {structure.targets.join(', ')}
                </span>
                {hasContext && <span className="hidden truncate text-dim xl:inline">{t('contextOf', { tags: structure.contexts.join(', ') })}</span>}
              </span>
            )}
          </Button>
        )}
        <div className="hidden flex-[1_1_8px] md:block" />
        <div className="flex shrink-0 items-center gap-2 text-[13px] text-dim">
          <span className="hidden xl:inline">{t('to')}</span>
          <Select aria-label={t('to')} name="target" className="w-[150px] max-w-full text-sm xl:w-[190px]" value={settings.target} disabled={state.translating} onChange={(value) => void run(() => api('/api/settings', 'PUT', { target: value }))} options={Object.entries(settings.targets).map(([label, value]) => ({ value, label }))} />
        </div>
        <div className="flex shrink-0 items-center gap-2 text-[13px] text-dim">
          <span className="hidden xl:inline">{t('with')}</span>
          <Select aria-label={t('with')} name="provider" className="w-[150px] max-w-full text-sm xl:w-[230px]" value={settings.provider} disabled={state.translating} onChange={(value) => void run(() => api('/api/settings', 'PUT', { provider: value }))} options={settings.providers.map((provider) => ({ value: provider.id, label: providerLabel(provider.id, t) }))} />
        </div>
        {state.translating ? (
          <Button className="shrink-0" onClick={() => void run(() => api('/api/translate/cancel', 'POST'))}>{t('cancelTranslation')}</Button>
        ) : (
          <Button variant="primary" className="shrink-0" disabled={toTranslate === 0} onClick={() => void run(() => api('/api/translate', 'POST', {}))}>
            {toTranslate ? t('translatePending', { n: toTranslate }) : t('allTranslated')}
          </Button>
        )}
        <Button className="shrink-0" onClick={() => void exportXml()} disabled={state.translating}>
          {t('exportXml')}
        </Button>
        <IconButton label={t('settings')} onClick={onOpenSettings}>
          <SlidersHorizontal aria-hidden="true" size={18} />
        </IconButton>
      </header>

      <div className="flex flex-wrap items-center gap-4 px-5 pb-3 pt-3.5">
        <div className="flex flex-wrap gap-1.5">
          {filters.map(([id, label, count]) => {
            const on = filter === id
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => setFilter(id)}
                className={cx(
                  'flex min-h-11 items-center gap-2 rounded-[10px] border px-3.5 text-sm font-medium transition-colors',
                  on ? 'border-ink bg-ink text-ground' : 'border-edge text-soft hover:bg-raised',
                )}
              >
                {t(label)}
                <span className={cx('font-mono text-xs', on ? 'opacity-70' : 'text-dim')}>{count}</span>
              </button>
            )
          })}
        </div>
        <div className="flex min-w-[180px] flex-[1_1_220px] flex-col gap-1.5">
          <div aria-hidden="true" className="flex h-1.5 gap-[3px]">
            <div className="rounded-[3px] bg-accent transition-[width]" style={{ width: `${(counts.confirmed / total) * 100}%` }} />
            <div className="rounded-[3px] bg-warn-bar transition-[width]" style={{ width: `${(counts.translated / total) * 100}%` }} />
            <div className="flex-1 rounded-[3px] bg-track" />
          </div>
          <div className="text-xs text-dim">
            {t('progress', { c: counts.confirmed, r: counts.translated, p: counts.pending + counts.translating + counts.error })}
          </div>
        </div>
        {fields.length > 1 && (
          <Select aria-label={t('fieldFilter')} name="field" className="w-[240px] max-w-full font-mono text-[13px]" value={field} onChange={setField} options={fieldOptions} />
        )}
        <label className={cx(fieldClass, 'search-field flex flex-[0_1_300px] items-center gap-2 border-edge bg-chip text-dim')}>
          <Search aria-hidden="true" size={16} className="shrink-0" />
          <input
            type="search"
            aria-label={t('search')}
            placeholder={t('search')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-faint"
          />
        </label>
      </div>

      {/* Side by side when there is room, each pane scrolling on its own; stacked below that. */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 px-5 pb-4 lg:grid lg:grid-cols-[minmax(0,2.6fr)_minmax(340px,1fr)] lg:grid-rows-[minmax(0,1fr)]">
        <section aria-label={t('filterAll')} className={cx(cardClass, 'flex h-[60vh] min-w-0 flex-col overflow-x-auto lg:h-auto lg:min-h-0')}>
          <div className="flex min-h-0 min-w-[680px] flex-1 flex-col">
            <div className={cx(GRID, eyebrowClass, 'border-b border-line px-4 py-3')}>
              <span>{t('colNumber')}</span>
              <span>{t(hasContext ? 'colContext' : 'colField')}</span>
              <span>{t('colOriginal')}</span>
              <span>{t('colTranslation')}</span>
              <span>{t('colState')}</span>
            </div>
            {visible.length === 0 ? (
              <div className="px-6 py-12 text-center text-dim">
                <div className="mb-1.5 text-[15px] font-medium text-ink">{t('emptyTitle')}</div>
                <div>{t('emptyBody')}</div>
              </div>
            ) : (
              <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
                <div className="relative" style={{ height: virtualizer.getTotalSize() }}>
                  {virtualizer.getVirtualItems().map((item) => {
                    const entry = visible[item.index]
                    const on = entry.id === selectedId
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        aria-current={on}
                        onClick={() => select(entry.id)}
                        onKeyDown={(event) => {
                          if (event.key === 'ArrowDown') move(1)
                          else if (event.key === 'ArrowUp') move(-1)
                          else return
                          event.preventDefault()
                        }}
                        className={cx(
                          GRID,
                          'absolute left-0 top-0 w-full border-b border-rowline px-4 py-[13px] text-left text-sm leading-[1.45] -outline-offset-2',
                          on ? 'bg-raised shadow-[inset_0_0_0_1px_var(--accent)]' : 'hover:bg-raised/50',
                        )}
                        style={{ height: ROW_HEIGHT, transform: `translateY(${item.start}px)` }}
                      >
                        <span className="pt-0.5 font-mono text-xs text-dim">{String(entry.n).padStart(2, '0')}</span>
                        <span className="truncate font-medium">{contextOf(entry)}</span>
                        <span className="line-clamp-2 text-soft">{entry.original}</span>
                        <span className={cx('line-clamp-2', entry.translation ? 'text-ink' : 'text-faint')}>
                          {entry.translation || t('noTranslation')}
                        </span>
                        <StatusMark status={entry.status} t={t} />
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </section>

        <aside aria-label={t('translation')} className={cx(cardClass, 'flex min-h-[380px] min-w-0 flex-col gap-4 overflow-y-auto p-[18px] lg:min-h-0')}>
          {!selected ? (
            <p className="m-auto max-w-[260px] text-center text-dim">{t('nothingSelected')}</p>
          ) : (
            <>
              <div className="flex items-center gap-2.5">
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-dim">{t('entryOf', { n: selected.n, total: state.total })}</div>
                  <div className="truncate text-lg font-semibold tracking-[-0.01em]">{contextOf(selected)}</div>
                </div>
                <IconButton label={t('previous')} onClick={() => move(-1)}>
                  <ChevronUp aria-hidden="true" size={16} />
                </IconButton>
                <IconButton label={t('next')} onClick={() => move(1)}>
                  <ChevronDown aria-hidden="true" size={16} />
                </IconButton>
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 text-xs text-dim">
                  {t('original')}
                  <span className="rounded-md border border-edge px-1.5 py-px font-mono">{selected.sourceTag}</span>
                </div>
                <p className="m-0 max-h-[30vh] overflow-y-auto whitespace-pre-wrap rounded-[10px] bg-ground px-3.5 py-3 text-[15px] leading-normal text-soft">
                  {selected.original}
                </p>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="translation" className="text-xs text-dim">
                  {t('translation')}
                </label>
                <textarea
                  id="translation"
                  rows={5}
                  value={draft}
                  disabled={selectedBusy}
                  placeholder={t('translationPlaceholder')}
                  onChange={(event) => {
                    editing.current = true
                    setDraft(event.target.value)
                  }}
                  onBlur={() => {
                    commitDraft()
                    editing.current = false
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                      event.preventDefault()
                      confirm()
                    }
                  }}
                  className={cx(fieldClass, 'w-full resize-y py-3 text-[15px] leading-normal')}
                />
                {selected.status === 'error' && selected.error && <p className="m-0 text-[13px] text-bad">{selected.error}</p>}
                {matches.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-dim">
                    <span>{t('glossaryHere')}</span>
                    {matches.map((term) => (
                      <span key={term.original} className="rounded-md bg-raised px-2 py-0.5 font-mono text-ink">
                        {term.original} → {term.translation}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <Suggestions
                entry={selected}
                onUse={(text) => {
                  editing.current = false
                  setDraft(text)
                  void run(() => api('/api/entries/edit', 'POST', { id: selected.id, text, source: 'memory' }))
                }}
              />

              <History
                entry={selected}
                onRestore={(text) => {
                  editing.current = false
                  setDraft(text)
                  void run(() => api('/api/entries/edit', 'POST', { id: selected.id, text }))
                }}
              />

              <div className="mt-auto flex gap-2.5">
                <Button
                  className="flex-none"
                  disabled={selectedBusy || state.translating}
                  onClick={() => {
                    editing.current = false
                    void run(() => api('/api/entries/translate', 'POST', { id: selected.id }))
                  }}
                >
                  {t('translate')}
                </Button>
                <Button variant="primary" className="min-w-0 flex-1 px-3" disabled={selectedBusy || !draft.trim()} onClick={confirm}>
                  {t('confirmNext')}
                  <span className="rounded-[5px] bg-black/15 px-1.5 py-0.5 font-mono text-[11px] font-medium">Ctrl Enter</span>
                </Button>
              </div>
            </>
          )}
        </aside>
      </div>

      <footer className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-5 py-2.5 text-xs text-dim">
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
          {t('savedCheckpoint')}
        </span>
        {state.activity && (
          <span className={cx('min-w-0 max-w-[46ch] truncate', state.activity.level === 'error' && 'text-bad')} title={state.activity.text}>
            {state.activity.text}
          </span>
        )}
        <span className="flex-1" />
        {state.update.available && (
          <button type="button" onClick={onOpenUpdate} className="text-ink underline underline-offset-4">
            {t('newVersion', { v: state.update.version })}
          </button>
        )}
        <button type="button" onClick={onOpenGlossary} className={buttonClass('quiet', 'min-h-0 px-0 text-xs underline underline-offset-4')}>
          {t('glossaryTerms', { n: settings.glossaryCount })}
        </button>
        <span>{t('structureKept')}</span>
      </footer>
    </div>
  )
}
