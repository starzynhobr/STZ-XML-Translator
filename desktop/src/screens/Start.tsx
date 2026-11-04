import FloatingPanel from '@/components/FloatingPanel'
import StzLabsBadge from '@/components/StzLabsBadge'
import { Check, ChevronDown, ChevronRight, FileText, Gamepad2, SlidersHorizontal, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button, IconButton, LogoMark, cardClass, cx, eyebrowClass, fieldClass } from '@/components/ui'
import { api, type Analysis, type EngineState, type FieldKind, type FieldRole, type Group, type OpenedXml, type Preset, type Preview, type TagPlan } from '@/lib/bridge'
import { XML_FILTER, formatSize, pickFile } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'
import type { MessageKey } from '@/lib/messages'

interface Props {
  floating?: boolean
  /** A file chosen elsewhere (a project's file list) to open right away. */
  initialPath?: string
  state: EngineState
  refresh: () => Promise<void>
  onLoaded: () => void
  onBack: (() => void) | null
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

const KIND_LABEL: Record<FieldKind, MessageKey> = {
  text: 'kindText',
  name: 'kindName',
  id: 'kindId',
  number: 'kindNumber',
  flag: 'kindFlag',
  path: 'kindPath',
  empty: 'kindEmpty',
  code: 'kindCode',
}

const ROLES: [FieldRole, MessageKey][] = [
  ['translate', 'roleTranslate'],
  ['context', 'roleContext'],
  ['ignore', 'roleIgnore'],
]

const groupOf = (plan: TagPlan): Group => ({
  parent: plan.tag,
  targets: plan.fields.filter((f) => f.role === 'translate').map((f) => f.tag),
  contexts: plan.fields.filter((f) => f.role === 'context').map((f) => f.tag),
})

/** Lays a saved selection (from the bench or a preset) over the suggestion. */
function applyGroups(plans: TagPlan[], groups: Group[]): TagPlan[] {
  const byTag = new Map(groups.map((group) => [group.parent, group]))
  return plans.map((plan) => {
    const group = byTag.get(plan.tag)
    if (!group) return { ...plan, selected: false }
    return {
      ...plan,
      selected: true,
      fields: plan.fields.map((field) => ({
        ...field,
        role: group.targets.includes(field.tag) ? 'translate' : group.contexts.includes(field.tag) ? 'context' : 'ignore',
      })),
    }
  })
}

function RoleSwitch({ field, onChange }: { field: { tag: string; role: FieldRole }; onChange: (role: FieldRole) => void }) {
  const t = useT()
  return (
    <div role="radiogroup" aria-label={field.tag} className="flex shrink-0 overflow-hidden rounded-[9px] border border-edge">
      {ROLES.map(([role, label]) => {
        const on = field.role === role
        return (
          <button
            key={role}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(role)}
            className={cx(
              'min-h-9 px-2.5 text-xs font-medium transition-colors',
              on && role === 'translate' && 'bg-accent text-on-accent',
              on && role === 'context' && 'bg-warn/15 text-warn',
              on && role === 'ignore' && 'bg-raised text-soft',
              !on && 'text-dim hover:bg-raised hover:text-ink',
            )}
          >
            {t(label)}
          </button>
        )
      })}
    </div>
  )
}

function TagCard({ plan, open, advanced, onToggle, onOpen, onRole }: {
  plan: TagPlan
  open: boolean
  advanced: boolean
  onToggle: () => void
  onOpen: () => void
  onRole: (field: string, role: FieldRole) => void
}) {
  const t = useT()
  const translate = plan.fields.filter((f) => f.role === 'translate')
  const context = plan.fields.filter((f) => f.role === 'context')
  const shown = plan.fields.filter((f) => advanced || !f.technical || f.role !== 'ignore')
  const hidden = plan.fields.length - shown.length
  return (
    <li className={cx(cardClass, 'shrink-0 overflow-hidden', plan.selected && 'border-edge-strong')}>
      <div className="flex items-stretch">
        <button
          type="button"
          aria-pressed={plan.selected}
          aria-label={t('useTag', { tag: plan.tag })}
          onClick={onToggle}
          className="flex shrink-0 items-center px-3.5 hover:bg-raised"
        >
          <span className={cx('flex size-5 items-center justify-center rounded-[6px] border', plan.selected ? 'border-accent bg-accent text-on-accent' : 'border-edge-strong')}>
            {plan.selected && <Check aria-hidden="true" size={13} strokeWidth={3} />}
          </span>
        </button>
        <button type="button" aria-expanded={open} onClick={onOpen} className="flex min-w-0 flex-1 flex-col gap-1.5 py-3 pr-3.5 text-left hover:bg-raised/60">
          <span className="flex w-full items-baseline gap-2">
            <span className="font-mono text-sm font-semibold">{plan.tag}</span>
            <span className="text-[13px] text-dim">{t('tagTexts', { n: plan.texts })}</span>
            <span className="flex-1" />
            {open ? <ChevronDown aria-hidden="true" size={16} className="text-dim" /> : <ChevronRight aria-hidden="true" size={16} className="text-dim" />}
          </span>
          <span className="flex flex-wrap gap-1.5">
            {translate.map((f) => <span key={f.tag} className="rounded-md bg-accent/15 px-1.5 py-0.5 font-mono text-xs text-accent">{f.tag}</span>)}
            {context.map((f) => <span key={f.tag} className="rounded-md border border-warn/50 px-1.5 py-px font-mono text-xs text-warn">{f.tag}</span>)}
            {!translate.length && <span className="text-xs text-dim">{t('noFieldChosen')}</span>}
          </span>
        </button>
      </div>
      {open && (
        <ul className="m-0 list-none divide-y divide-line border-t border-line p-0">
          {shown.map((field) => (
            <li key={field.tag} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3.5 py-2.5">
              <div className="min-w-0 flex-[1_1_220px]">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[13px]">{field.tag}</span>
                  <span className={cx('text-[11px] uppercase tracking-[0.04em]', field.technical ? 'text-dim' : 'text-soft')}>{t(KIND_LABEL[field.kind])}</span>
                </div>
                <div className="truncate text-xs text-dim" title={field.sample}>{field.sample || '—'}</div>
              </div>
              <RoleSwitch field={field} onChange={(role) => onRole(field.tag, role)} />
              {field.technical && field.role === 'translate' && (
                <p role="alert" className="m-0 basis-full text-xs text-warn">{t('technicalWarning')}</p>
              )}
            </li>
          ))}
          {hidden > 0 && <li className="px-3.5 py-2 text-xs text-dim">{t('hiddenTechnical', { n: hidden })}</li>}
        </ul>
      )}
    </li>
  )
}

export default function Start({ floating = false, initialPath, state, refresh, onLoaded, onBack, onOpenSettings, onOpenGlossary }: Props) {
  const t = useT()
  const originalPath = useRef(state.file?.path)
  const initialized = useRef(false)
  const [file, setFile] = useState<OpenedXml | null>(null)
  const [plans, setPlans] = useState<TagPlan[]>([])
  const [profile, setProfile] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [advanced, setAdvanced] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [naming, setNaming] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [busy, setBusy] = useState(false)

  const fail = useCallback((error: unknown) => toast.error(errorText(t, error)), [t])

  const openPath = useCallback(
    async (path: string, keep?: Group[]) => {
      setBusy(true)
      try {
        const opened = await api<OpenedXml>('/api/xml/open', 'POST', { path })
        const analysis = await api<Analysis>('/api/xml/analyze')
        setFile(opened)
        setProfile(analysis.profile.name)
        const next = keep?.length ? applyGroups(analysis.tags, keep) : analysis.tags
        setPlans(next)
        setOpen(next.find((plan) => plan.selected)?.tag ?? null)
      } catch (error) {
        fail(error)
      } finally {
        setBusy(false)
      }
    },
    [fail],
  )

  // Coming back from the bench: show the file and the tags that are in use.
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    void api<{ presets: Preset[] }>('/api/presets').then((data) => setPresets(data.presets), fail)
    if (initialPath) void openPath(initialPath)
    else if (state.file) void openPath(state.file.path, state.structure?.groups)
    // Runs once: later snapshots must not overwrite what the user is choosing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const groups = useMemo(() => plans.filter((plan) => plan.selected).map(groupOf).filter((group) => group.targets.length), [plans])

  useEffect(() => {
    if (!file || !groups.length) {
      setPreview(null)
      return
    }
    let stale = false
    api<Preview>('/api/xml/preview-groups', 'POST', { groups }).then(
      (data) => !stale && setPreview(data),
      () => !stale && setPreview(null),
    )
    return () => {
      stale = true
    }
  }, [file, groups])

  const pick = async () => {
    const path = await pickFile(XML_FILTER)
    if (path) await openPath(path)
  }

  const update = (tag: string, change: (plan: TagPlan) => TagPlan) => setPlans((current) => current.map((plan) => (plan.tag === tag ? change(plan) : plan)))

  const toggle = (plan: TagPlan) => update(plan.tag, (p) => ({ ...p, selected: !p.selected }))

  const setRole = (tag: string, field: string, role: FieldRole) =>
    update(tag, (plan) => {
      const fields = plan.fields.map((f) => (f.tag === field ? { ...f, role } : f))
      // Choosing something to translate in a tag means using that tag.
      return { ...plan, fields, selected: role === 'translate' ? true : plan.selected && fields.some((f) => f.role === 'translate') }
    })

  const load = async () => {
    setBusy(true)
    try {
      await api('/api/xml/load', 'POST', { groups })
      await refresh()
      onLoaded()
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  const applyPreset = (preset: Preset) => {
    if (!plans.some((plan) => plan.tag === preset.parent)) {
      toast.error(t('error.preset_invalid'))
      return
    }
    setPlans((current) => applyGroups(current, [preset]))
    setOpen(preset.parent)
  }

  const savePreset = async () => {
    const [group] = groups
    try {
      const data = await api<{ presets: Preset[] }>('/api/presets', 'POST', { label: presetName, ...group })
      setPresets(data.presets)
      setNaming(false)
      setPresetName('')
      toast.success(t('toastPresetSaved'))
    } catch (error) {
      fail(error)
    }
  }

  const removePreset = async (preset: Preset) => {
    await api<{ presets: Preset[] }>(`/api/presets/${preset.id}`, 'DELETE').then((data) => setPresets(data.presets), fail)
  }

  const lines = preview?.lines ?? 0
  const usablePresets = presets.filter((preset) => plans.some((plan) => plan.tag === preset.parent))
  const visible = plans.filter((plan) => advanced || plan.useful || plan.selected)
  const technicalTags = plans.length - visible.length
  const roleOf = useMemo(() => {
    const roles = new Map<string, Map<string, FieldRole>>()
    for (const group of groups) roles.set(group.parent, new Map([...group.targets.map((tag) => [tag, 'translate'] as const), ...group.contexts.map((tag) => [tag, 'context'] as const)]))
    return roles
  }, [groups])

  const cancel = async () => {
    if (busy) return
    setBusy(true)
    try {
      if (originalPath.current && file?.path !== originalPath.current) {
        await api('/api/xml/open', 'POST', { path: originalPath.current })
        await refresh()
      }
      onBack?.()
    } catch (error) { fail(error) }
    finally { setBusy(false) }
  }

  const content = (
    <div className="flex min-h-full flex-col">
      {floating ? <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
        <h1 className="m-0 text-xl font-semibold">{t('startTitle')}</h1>
        <IconButton label={t('close')} disabled={busy} onClick={() => void cancel()}><X aria-hidden="true" size={18} /></IconButton>
      </header> : <header className="relative flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <LogoMark />
        <span className="font-semibold tracking-[-0.01em]">XML Translator</span>
        <div className="absolute left-1/2 hidden -translate-x-1/2 md:block">
          <StzLabsBadge version={state.version} locale={state.settings.locale} />
        </div>
        <div className="flex-1" />
        {onBack && <Button onClick={() => void cancel()}>
          {state.loaded ? t('backToBench') : state.project?.name ?? t('projectsTitle')}
        </Button>}
        <Button onClick={onOpenGlossary}>{t('glossary')}</Button>
        <IconButton label={t('settings')} onClick={onOpenSettings}>
          <SlidersHorizontal aria-hidden="true" size={18} />
        </IconButton>
      </header>}

      {!file ? (
        <div className="m-auto flex max-w-[460px] flex-col items-center gap-4 px-5 py-16 text-center">
          <FileText aria-hidden="true" size={40} strokeWidth={1.4} className="text-dim" />
          <h1 className="m-0 text-[32px] font-semibold leading-[1.15] tracking-[-0.03em]">{t('pickTitle')}</h1>
          <p className="m-0 text-[15px] text-dim">{t('pickBody')}</p>
          <Button variant="primary" className="mt-2 min-h-12 px-6 text-[15px]" disabled={busy} onClick={() => void pick()}>
            {t('pickButton')}
          </Button>
        </div>
      ) : (
        <div className={cx('mx-auto flex w-full max-w-[1280px] flex-1 items-stretch gap-5 px-5', floating ? 'flex-col py-5 md:flex-row' : 'flex-wrap py-9')}>
          <section className={cx('flex min-w-0 flex-col', floating ? 'gap-4 md:w-[46%] md:shrink-0' : 'flex-[1_1_440px] gap-5')}>
            {!floating && <div>
              <h1 className="m-0 mb-2 text-[32px] font-semibold leading-[1.15] tracking-[-0.03em]">{t('startTitle')}</h1>
              <p className="m-0 text-[15px] text-dim">{t('startSubtitleAuto')}</p>
            </div>}

            <div className={cx(cardClass, 'flex flex-wrap items-center gap-3.5 px-4 py-3.5')}>
              <FileText aria-hidden="true" size={22} strokeWidth={1.8} className="shrink-0 text-soft" />
              <div className="min-w-0 flex-[1_1_180px]">
                <div className="truncate font-semibold" title={file.path}>{file.name}</div>
                <div className="text-[13px] text-dim">{formatSize(file.size)}</div>
                {profile && (
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-soft">
                    <Gamepad2 aria-hidden="true" size={13} />
                    {t('profileApplied', { name: profile })}
                  </div>
                )}
              </div>
              <Button disabled={busy} onClick={() => void pick()}>{t('changeFile')}</Button>
            </div>

            {usablePresets.length > 0 && (
              <div className="flex flex-col gap-2.5">
                <div className={eyebrowClass}>{t('usePreset')}</div>
                <div className="flex flex-wrap gap-2">
                  {usablePresets.map((preset) => (
                    <span key={preset.id} className="flex items-stretch overflow-hidden rounded-[10px] border border-edge bg-chip">
                      <button type="button" onClick={() => applyPreset(preset)} className="min-h-11 px-3.5 text-sm hover:bg-raised">{preset.label}</button>
                      <button
                        type="button"
                        aria-label={t('removePreset', { name: preset.label })}
                        title={t('removePreset', { name: preset.label })}
                        onClick={() => void removePreset(preset)}
                        className="flex w-9 items-center justify-center border-l border-edge text-dim hover:bg-raised hover:text-ink"
                      >
                        <X aria-hidden="true" size={14} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {plans.length === 0 ? (
              <p className="m-0 text-dim">{t('noRepeating')}</p>
            ) : (
              <div className="flex flex-col gap-2.5">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-semibold">{t('whatToTranslate')}</span>
                  <span className="text-[13px] text-dim">{t('whatToTranslateHint')}</span>
                </div>
                {visible.length === 0 && <p className="m-0 text-dim">{t('noTextFound')}</p>}
                <ul className={cx('m-0 flex list-none flex-col gap-2 p-0', floating && 'max-h-[340px] overflow-y-auto pr-1')}>
                  {visible.map((plan) => (
                    <TagCard
                      key={plan.tag}
                      plan={plan}
                      open={open === plan.tag}
                      advanced={advanced}
                      onToggle={() => toggle(plan)}
                      onOpen={() => setOpen(open === plan.tag ? null : plan.tag)}
                      onRole={(field, role) => setRole(plan.tag, field, role)}
                    />
                  ))}
                </ul>
                <label className="flex cursor-pointer items-center gap-2 self-start text-[13px] text-dim">
                  <input type="checkbox" checked={advanced} onChange={(event) => setAdvanced(event.target.checked)} className="accent-[var(--accent)]" />
                  {technicalTags > 0 && !advanced ? t('showTechnicalCount', { n: technicalTags }) : t('showTechnical')}
                </label>
              </div>
            )}

            <div className="mt-auto flex flex-wrap gap-2.5">
              {naming ? (
                <form
                  className="flex flex-1 flex-wrap gap-2.5"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void savePreset()
                  }}
                >
                  <input
                    autoFocus
                    aria-label={t('presetName')}
                    placeholder={t('presetName')}
                    value={presetName}
                    onChange={(event) => setPresetName(event.target.value)}
                    className={cx(fieldClass, 'min-h-12 min-w-0 flex-[1_1_180px]')}
                  />
                  <Button type="submit" variant="primary" className="min-h-12" disabled={!presetName.trim() || groups.length !== 1}>{t('save')}</Button>
                  <Button className="min-h-12" onClick={() => setNaming(false)}>{t('cancel')}</Button>
                </form>
              ) : (
                <>
                  <Button variant="primary" className="min-h-12 flex-[2_1_200px] px-5 text-[15px]" disabled={busy || !groups.length || lines === 0} onClick={() => void load()}>
                    {groups.length ? t('loadEntries', { n: lines }) : t('chooseField')}
                  </Button>
                  {groups.length === 1 && (
                    <Button className="min-h-12 flex-[1_1_150px]" onClick={() => setNaming(true)}>{t('saveAsPreset')}</Button>
                  )}
                </>
              )}
            </div>
          </section>

          <section aria-label={t('preview')} className={cx(cardClass, 'flex min-w-0 flex-col overflow-hidden', floating ? 'max-h-[560px] flex-1' : 'flex-[999_1_520px]')}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-[18px] py-3.5">
              <span className="font-semibold">{t('preview')}</span>
              {preview && <span className="text-dim">{t('previewCounts', { r: preview.records, l: preview.lines })}</span>}
              <span className="flex-1" />
              <span className="flex items-center gap-1.5 text-xs text-soft">
                <span aria-hidden="true" className="size-2.5 rounded-[3px] bg-accent" />
                {t('legendTranslate')}
              </span>
              <span className="flex items-center gap-1.5 text-xs text-soft">
                <span aria-hidden="true" className="size-2.5 rounded-[3px] border-[1.5px] border-warn" />
                {t('legendContext')}
              </span>
            </div>
            <div className="flex-1 overflow-auto px-[18px] py-5">
              {!preview && <p className="m-0 text-dim">{t('previewEmpty')}</p>}
              <pre className="m-0 whitespace-pre-wrap break-words font-mono text-sm leading-loose text-faint">
                {preview?.sample.map((record, index) => {
                  const roles = roleOf.get(record.tag)
                  const fields = record.fields.filter((field) => advanced || roles?.has(field.tag))
                  const hidden = record.fields.length - fields.length
                  return (
                    <span key={index}>
                      {'<'}
                      {record.tag}
                      {Object.entries(record.attributes).map(([name, value]) => ` ${name}="${value}"`)}
                      {'>\n'}
                      {hidden > 0 && <span className="text-dim">{`  … ${t('previewHidden', { n: hidden })}\n`}</span>}
                      {fields.map((field, at) => {
                        const role = roles?.get(field.tag)
                        return (
                          <span key={at}>
                            {'  <'}
                            {field.tag}
                            {'>'}
                            <span
                              className={cx(
                                role === 'translate' && 'rounded-md bg-accent px-1.5 py-[3px] text-on-accent',
                                role === 'context' && 'rounded-md border-[1.5px] border-warn px-1.5 py-0.5 text-warn',
                              )}
                            >
                              {field.text}
                            </span>
                            {'</'}
                            {field.tag}
                            {'>\n'}
                          </span>
                        )
                      })}
                      {'</'}
                      {record.tag}
                      {'>\n\n'}
                    </span>
                  )
                })}
              </pre>
            </div>
            <div className="border-t border-line px-[18px] py-3 text-[13px] text-dim">{t('keepNote')}</div>
          </section>
        </div>
      )}
    </div>
  )
  return floating
    ? <FloatingPanel label={t('startTitle')} onDismiss={() => void cancel()} dismissible={!busy} className="w-[min(1080px,calc(100vw-48px))]">{content}</FloatingPanel>
    : content
}
