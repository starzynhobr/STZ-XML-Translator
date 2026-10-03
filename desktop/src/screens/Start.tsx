import { Check, FileText, SlidersHorizontal, X } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { Button, IconButton, LogoMark, cardClass, cx, eyebrowClass, fieldClass } from '@/components/ui'
import { api, type EngineState, type OpenedXml, type Preset, type Preview } from '@/lib/bridge'
import { XML_FILTER, formatSize, pickFile } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'

interface Props {
  state: EngineState
  refresh: () => Promise<void>
  onLoaded: () => void
  onBack: (() => void) | null
  onOpenSettings: () => void
  onOpenGlossary: () => void
}

function TagToggle({ on, tone, onClick, children }: { on: boolean; tone: 'translate' | 'context'; onClick: () => void; children: ReactNode }) {
  const selected = tone === 'translate' ? 'border-accent bg-accent font-medium text-on-accent' : 'border-warn font-medium text-warn'
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cx(
        'flex min-h-11 items-center gap-2 rounded-[10px] border px-3.5 font-mono text-[13px] transition-colors',
        on ? selected : 'border-edge text-soft hover:bg-raised',
      )}
    >
      {on && <Check aria-hidden="true" size={14} strokeWidth={2.4} />}
      {children}
    </button>
  )
}

export default function Start({ state, refresh, onLoaded, onBack, onOpenSettings, onOpenGlossary }: Props) {
  const t = useT()
  const [file, setFile] = useState<OpenedXml | null>(null)
  const [parent, setParent] = useState('')
  const [children, setChildren] = useState<string[]>([])
  const [targets, setTargets] = useState<string[]>([])
  const [contexts, setContexts] = useState<string[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [naming, setNaming] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [busy, setBusy] = useState(false)

  const fail = useCallback((error: unknown) => toast.error(errorText(t, error)), [t])

  const chooseParent = useCallback(
    async (tag: string, keep?: { targets: string[]; contexts: string[] }) => {
      setParent(tag)
      const { tags } = await api<{ tags: string[] }>(`/api/xml/children?parent=${encodeURIComponent(tag)}`)
      setChildren(tags)
      setTargets((keep?.targets ?? []).filter((name) => tags.includes(name)))
      setContexts((keep?.contexts ?? []).filter((name) => tags.includes(name)))
    },
    [],
  )

  const openPath = useCallback(
    async (path: string, keep?: { parent: string; targets: string[]; contexts: string[] }) => {
      setBusy(true)
      try {
        const opened = await api<OpenedXml>('/api/xml/open', 'POST', { path })
        setFile(opened)
        const wanted = keep && opened.parents.some((item) => item.tag === keep.parent) ? keep.parent : opened.parents[0]?.tag
        if (wanted) await chooseParent(wanted, keep)
        else setParent('')
      } catch (error) {
        fail(error)
      } finally {
        setBusy(false)
      }
    },
    [chooseParent, fail],
  )

  // Coming back from the bench: show the file and fields that are in use.
  useEffect(() => {
    void api<{ presets: Preset[] }>('/api/presets').then((data) => setPresets(data.presets), fail)
    if (state.file) void openPath(state.file.path, state.structure ?? undefined)
    // Runs once: later snapshots must not overwrite what the user is choosing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!file || !parent) {
      setPreview(null)
      return
    }
    let stale = false
    api<Preview>('/api/xml/preview', 'POST', { parent, targets, contexts }).then(
      (data) => !stale && setPreview(data),
      () => !stale && setPreview(null),
    )
    return () => {
      stale = true
    }
  }, [file, parent, targets, contexts])

  const pick = async () => {
    const path = await pickFile(XML_FILTER)
    if (path) await openPath(path)
  }

  const toggle = (list: string[], tag: string) => (list.includes(tag) ? list.filter((name) => name !== tag) : [...list, tag])

  const load = async () => {
    setBusy(true)
    try {
      await api('/api/xml/load', 'POST', { parent, targets, contexts })
      await refresh()
      onLoaded()
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  const applyPreset = async (preset: Preset) => {
    if (!file?.parents.some((item) => item.tag === preset.parent)) {
      toast.error(t('error.preset_invalid'))
      return
    }
    await chooseParent(preset.parent, preset).catch(fail)
  }

  const savePreset = async () => {
    try {
      const data = await api<{ presets: Preset[] }>('/api/presets', 'POST', { label: presetName, parent, targets, contexts })
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
  const usablePresets = presets.filter((preset) => file?.parents.some((item) => item.tag === preset.parent))

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <LogoMark />
        <span className="font-semibold tracking-[-0.01em]">XML Translator</span>
        <div className="flex-1" />
        {onBack && <Button onClick={onBack}>{t('backToBench')}</Button>}
        <Button onClick={onOpenGlossary}>{t('glossary')}</Button>
        <IconButton label={t('settings')} onClick={onOpenSettings}>
          <SlidersHorizontal aria-hidden="true" size={18} />
        </IconButton>
      </header>

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
        <div className="mx-auto flex w-full max-w-[1280px] flex-1 flex-wrap items-stretch gap-5 px-5 py-9">
          <section className="flex min-w-0 flex-[1_1_420px] flex-col gap-[26px]">
            <div>
              <h1 className="m-0 mb-2 text-[32px] font-semibold leading-[1.15] tracking-[-0.03em]">{t('startTitle')}</h1>
              <p className="m-0 text-[15px] text-dim">{t('startSubtitle')}</p>
            </div>

            <div className={cx(cardClass, 'flex flex-wrap items-center gap-3.5 px-4 py-3.5')}>
              <FileText aria-hidden="true" size={22} strokeWidth={1.8} className="shrink-0 text-soft" />
              <div className="min-w-0 flex-[1_1_180px]">
                <div className="truncate font-semibold" title={file.path}>
                  {file.name}
                </div>
                <div className="text-[13px] text-dim">{t('fileSummary', { size: formatSize(file.size), n: file.parents.length })}</div>
              </div>
              <Button disabled={busy} onClick={() => void pick()}>
                {t('changeFile')}
              </Button>
            </div>

            {file.parents.length === 0 ? (
              <p className="m-0 text-dim">{t('noRepeating')}</p>
            ) : (
              <>
                {usablePresets.length > 0 && (
                  <div className="flex flex-col gap-2.5">
                    <div className={eyebrowClass}>{t('usePreset')}</div>
                    <div className="flex flex-wrap gap-2">
                      {usablePresets.map((preset) => (
                        <span key={preset.id} className="flex items-stretch overflow-hidden rounded-[10px] border border-edge bg-chip">
                          <button type="button" onClick={() => void applyPreset(preset)} className="min-h-11 px-3.5 text-sm hover:bg-raised">
                            {preset.label}
                          </button>
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

                <div className="flex flex-col gap-2">
                  <label htmlFor="parent" className="font-semibold">
                    {t('parentTag')}
                  </label>
                  <select
                    id="parent"
                    className={cx(fieldClass, 'max-w-[320px] font-mono')}
                    value={parent}
                    onChange={(event) => void chooseParent(event.target.value).catch(fail)}
                  >
                    {file.parents.map((item) => (
                      <option key={item.tag} value={item.tag}>
                        {item.tag} · {t('records', { n: item.count })}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="font-semibold">{t('fieldsToTranslate')}</div>
                  <div className="flex flex-wrap gap-2">
                    {children
                      .filter((tag) => !contexts.includes(tag))
                      .map((tag) => (
                        <TagToggle key={tag} tone="translate" on={targets.includes(tag)} onClick={() => setTargets(toggle(targets, tag))}>
                          {tag}
                        </TagToggle>
                      ))}
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <div>
                    <span className="font-semibold">{t('contextFields')}</span>
                    <span className="ml-2 text-dim">{t('contextHint')}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {children
                      .filter((tag) => !targets.includes(tag))
                      .map((tag) => (
                        <TagToggle key={tag} tone="context" on={contexts.includes(tag)} onClick={() => setContexts(toggle(contexts, tag))}>
                          {tag}
                        </TagToggle>
                      ))}
                  </div>
                </div>

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
                      <Button type="submit" variant="primary" className="min-h-12" disabled={!presetName.trim() || !targets.length}>
                        {t('save')}
                      </Button>
                      <Button className="min-h-12" onClick={() => setNaming(false)}>
                        {t('cancel')}
                      </Button>
                    </form>
                  ) : (
                    <>
                      <Button
                        variant="primary"
                        className="min-h-12 flex-[2_1_200px] px-5 text-[15px]"
                        disabled={busy || !targets.length || lines === 0}
                        onClick={() => void load()}
                      >
                        {targets.length ? t('loadEntries', { n: lines }) : t('chooseField')}
                      </Button>
                      <Button className="min-h-12 flex-[1_1_150px]" disabled={!targets.length} onClick={() => setNaming(true)}>
                        {t('saveAsPreset')}
                      </Button>
                    </>
                  )}
                </div>
              </>
            )}
          </section>

          <section aria-label={t('preview')} className={cx(cardClass, 'flex min-w-0 flex-[999_1_520px] flex-col overflow-hidden')}>
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
              <pre className="m-0 font-mono text-sm leading-loose text-faint">
                {preview?.sample.map((record, index) => (
                  <span key={index}>
                    {'<'}
                    {record.tag}
                    {Object.entries(record.attributes).map(([name, value]) => ` ${name}="${value}"`)}
                    {'>\n'}
                    {record.fields.map((field, at) => (
                      <span key={at}>
                        {'  <'}
                        {field.tag}
                        {'>'}
                        <span
                          className={cx(
                            targets.includes(field.tag) && 'rounded-md bg-accent px-1.5 py-[3px] text-on-accent',
                            contexts.includes(field.tag) && 'rounded-md border-[1.5px] border-warn px-1.5 py-0.5 text-warn',
                          )}
                        >
                          {field.text}
                        </span>
                        {'</'}
                        {field.tag}
                        {'>\n'}
                      </span>
                    ))}
                    {'</'}
                    {record.tag}
                    {'>\n'}
                  </span>
                ))}
              </pre>
            </div>
            <div className="border-t border-line px-[18px] py-3 text-[13px] text-dim">{t('keepNote')}</div>
          </section>
        </div>
      )}
    </div>
  )
}
