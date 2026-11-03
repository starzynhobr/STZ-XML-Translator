import Select from '@/components/Select'
import { CircleHelp, MessageSquare } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { Button, PageHeader, cardClass, cx, fieldClass, providerLabel, providerName } from '@/components/ui'
import { api, type Accent, type EngineState, type Preset, type Provider, type Theme } from '@/lib/bridge'
import { BACKUP_FILTER, CSV_FILTER, JSON_FILTER, openExternal, pickFile, pickSavePath } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'
import type { MessageKey } from '@/lib/messages'

interface Props {
  state: EngineState
  refresh: () => Promise<void>
  onBack: () => void
  onOpenUpdate: () => void
  onOpenHelp: () => void
}

const SECTIONS: [string, MessageKey][] = [
  ['appearance', 'appearance'],
  ['translation', 'translationSection'],
  ['data', 'dataSection'],
  ['updates', 'updates'],
  ['feedback', 'feedback'],
]
const THEMES: [Theme, MessageKey][] = [
  ['dark', 'themeDark'],
  ['light', 'themeLight'],
  ['system', 'themeSystem'],
]
const ACCENTS: [Accent, MessageKey, string][] = [
  ['teal', 'accentTeal', '#5eead4'],
  ['blue', 'accentBlue', '#7cb7ff'],
  ['amber', 'accentAmber', '#f5b642'],
]
const FEEDBACK_MIN = 10
const FEEDBACK_MAX = 400

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className={cx(cardClass, 'flex scroll-mt-6 flex-col gap-5 p-[22px]')}>
      <h2 className="m-0 text-[17px] font-semibold">{title}</h2>
      {children}
    </section>
  )
}

/** A setting: what it is on the left, its control on the right; stacks when narrow. */
function Row({ title, hint, htmlFor, children }: { title: string; hint?: string; htmlFor?: string; children: ReactNode }) {
  const heading = <span className="block font-medium">{title}</span>
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5">
      <div className="flex-[1_1_200px]">
        {htmlFor ? <label htmlFor={htmlFor}>{heading}</label> : heading}
        {hint && <div className="text-[13px] text-dim">{hint}</div>}
      </div>
      {children}
    </div>
  )
}

function ApiKeyRow({ provider, onSave }: { provider: Provider; onSave: (key: string) => Promise<void> }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState('')
  const name = providerName(provider.id)
  const inputId = `key-${name}`

  const submit = async () => {
    await onSave(key)
    setKey('')
    setOpen(false)
  }

  return (
    <div className="border-t border-line py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex-[1_1_140px] font-medium">{name}</span>
        <span className={cx('flex items-center gap-2 text-[13px]', provider.hasKey ? 'text-ink' : 'text-dim')}>
          {provider.hasKey && (
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6.25" className="fill-accent stroke-accent" strokeWidth="1.5" />
              <path d="M5 8.2l2 2 4-4.4" className="stroke-on-accent" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          {t(provider.hasKey ? 'keySaved' : 'noKey')}
        </span>
        <Button className="min-w-[104px]" aria-expanded={open} onClick={() => setOpen(!open)}>
          {t(provider.hasKey ? 'change' : 'add')}
        </Button>
      </div>
      {open && (
        <form
          className="mt-2.5 flex flex-wrap items-center gap-2.5"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <input
            id={inputId}
            autoFocus
            type="password"
            autoComplete="off"
            aria-label={t('apiKeyFor', { provider: name })}
            placeholder={t('apiKeyFor', { provider: name })}
            value={key}
            onChange={(event) => setKey(event.target.value)}
            className={cx(fieldClass, 'min-w-0 flex-[1_1_220px] font-mono')}
          />
          <Button type="submit" variant="primary" disabled={!key.trim()}>
            {t('save')}
          </Button>
          {provider.hasKey && (
            <Button
              onClick={() => {
                setOpen(false)
                void onSave('')
              }}
            >
              {t('remove')}
            </Button>
          )}
          {provider.keyUrl && (
            <button type="button" onClick={() => void openExternal(provider.keyUrl)} className="text-[13px] text-soft underline underline-offset-4 hover:text-ink">
              {t('whereToGetKey')}
            </button>
          )}
        </form>
      )}
    </div>
  )
}

export default function Settings({ state, refresh, onBack, onOpenUpdate, onOpenHelp }: Props) {
  const t = useT()
  const { settings, update } = state
  const [ollama, setOllama] = useState(settings.ollamaModel)
  const [context, setContext] = useState(settings.context)
  const [region, setRegion] = useState(settings.azureRegion)
  const [presetCount, setPresetCount] = useState(0)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [sending, setSending] = useState(false)

  const fail = (error: unknown) => toast.error(errorText(t, error))
  const change = (changes: Record<string, unknown>) => api('/api/settings', 'PUT', changes).then(refresh, fail)

  useEffect(() => {
    void api<{ presets: Preset[] }>('/api/presets').then(
      (data) => setPresetCount(data.presets.length),
      () => undefined,
    )
  }, [])

  const saveKey = async (provider: string, key: string) => {
    try {
      await api('/api/settings/api-key', 'PUT', { provider, key })
      await refresh()
      toast.success(t(key ? 'toastKeySaved' : 'toastKeyRemoved'))
    } catch (error) {
      fail(error)
    }
  }

  const exportBackup = async (format: 'json' | 'csv') => {
    const path = await pickSavePath(`translations.${format}`, format === 'json' ? JSON_FILTER : CSV_FILTER)
    if (!path) return
    await api('/api/backup/export', 'POST', { path, format }).then(() => toast.success(t('toastBackup')), fail)
  }

  const importBackup = async () => {
    const path = await pickFile(BACKUP_FILTER)
    if (!path) return
    try {
      const { count } = await api<{ count: number }>('/api/backup/import', 'POST', { path })
      await refresh()
      toast.success(t('toastImported', { n: count }))
    } catch (error) {
      fail(error)
    }
  }

  const exportPresets = async () => {
    const path = await pickSavePath('tag_presets.json', JSON_FILTER)
    if (!path) return
    await api('/api/presets/export', 'POST', { path }).then(() => toast.success(t('toastPresetsExported')), fail)
  }

  const importPresets = async () => {
    const path = await pickFile(JSON_FILTER)
    if (!path) return
    try {
      const result = await api<{ imported: number; skipped: number; presets: Preset[] }>('/api/presets/import', 'POST', { path })
      setPresetCount(result.presets.length)
      toast.success(t('toastPresetsImported', { i: result.imported, s: result.skipped }))
    } catch (error) {
      fail(error)
    }
  }

  const sendFeedback = async () => {
    setSending(true)
    try {
      await api('/api/feedback', 'POST', { text: feedback })
      // Clear only after the server accepts the message; keep failures for a retry.
      setFeedback('')
      setFeedbackOpen(false)
      toast.success(t('toastFeedback'))
    } catch (error) {
      fail(error)
    } finally {
      setSending(false)
    }
  }

  const keyed = settings.providers.filter((provider) => provider.needsKey)
  const hasOllama = settings.providers.some((provider) => provider.id.includes('Local'))
  const gemini = settings.providers.find((provider) => provider.id === 'Gemini')
  const checking = update.status === 'checking'
  const updateLine = update.available
    ? t('updateAvailable', { v: update.version })
    : update.status === 'error'
      ? t('updateError')
      : update.checkedAt
        ? t('upToDate')
        : t('notChecked')
  const feedbackLength = feedback.trim().length

  return (
    <div className="flex min-h-full flex-col">
      <PageHeader title={t('settings')} onBack={onBack} backLabel={state.loaded ? t('backToBench') : t('back')}>
        <Button onClick={onOpenHelp}>
          <CircleHelp aria-hidden="true" size={16} />
          {t('helpTitle')}
        </Button>
      </PageHeader>
      <div className="mx-auto flex w-full max-w-[1080px] flex-1 flex-wrap items-start gap-x-10 gap-y-6 px-5 pb-12 pt-8">
        <nav aria-label={t('settings')} className="flex max-w-[220px] flex-[1_1_180px] flex-col gap-0.5 lg:sticky lg:top-6">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="flex min-h-11 items-center rounded-[10px] px-3 text-soft no-underline hover:bg-raised hover:text-ink">
              {t(label)}
            </a>
          ))}
        </nav>

        <div className="flex min-w-0 flex-[999_1_520px] flex-col gap-5">
          <Section id="appearance" title={t('appearance')}>
            <Row title={t('theme')} hint={t('themeHint')}>
              <div className="flex flex-wrap gap-1.5">
                {THEMES.map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={settings.theme === id}
                    onClick={() => void change({ theme: id })}
                    className={cx(
                      'min-h-11 rounded-[10px] border px-4 text-sm font-medium transition-colors',
                      settings.theme === id ? 'border-ink bg-ink text-ground' : 'border-edge text-soft hover:bg-raised',
                    )}
                  >
                    {t(label)}
                  </button>
                ))}
              </div>
            </Row>
            <Row title={t('accent')} hint={t('accentHint')}>
              <div className="flex gap-2">
                {ACCENTS.map(([id, label, color]) => (
                  <button
                    key={id}
                    type="button"
                    aria-label={t(label)}
                    title={t(label)}
                    aria-pressed={settings.accent === id}
                    onClick={() => void change({ accent: id })}
                    className={cx('size-11 rounded-xl border-2 shadow-[inset_0_0_0_3px_var(--panel)]', settings.accent === id ? 'border-ink' : 'border-transparent')}
                    style={{ background: color }}
                  />
                ))}
              </div>
            </Row>
            <Row title={t('appLanguage')} htmlFor="app-lang">
              <Select id="app-lang" className="w-[240px] max-w-full" value={settings.locale} onChange={(value) => void change({ locale: value })} options={Object.entries(settings.locales).map(([label, value]) => ({ value, label }))} />
            </Row>
          </Section>

          <Section id="translation" title={t('translationSection')}>
            <Row title={t('defaultProvider')} htmlFor="provider">
              <Select id="provider" className="w-[240px] max-w-full" value={settings.provider} onChange={(value) => void change({ provider: value })} options={settings.providers.map((provider) => ({ value: provider.id, label: providerLabel(provider.id, t) }))} />
            </Row>
            <div className="flex flex-col">
              <div className="font-medium">{t('apiKeys')}</div>
              <div className="mb-2.5 text-[13px] text-dim">{t('apiKeysHint')}</div>
              {keyed.map((provider) => (
                <ApiKeyRow key={provider.id} provider={provider} onSave={(key) => saveKey(provider.id, key)} />
              ))}
            </div>
            {gemini?.hasKey && settings.models.length > 0 && (
              <Row title={t('geminiModel')} htmlFor="gemini-model">
                <Select id="gemini-model" className="max-w-[280px]" value={settings.model} onChange={(value) => void change({ model: value })} options={settings.models.map((model) => ({ value: model.label, label: `${model.label} · ${t(model.paid ? 'paid' : 'free')}` }))} />
              </Row>
            )}
            {hasOllama && (
              <Row title={t('ollamaModel')} hint={t('ollamaHint')} htmlFor="ollama">
                <input
                  id="ollama"
                  value={ollama}
                  onChange={(event) => setOllama(event.target.value)}
                  onBlur={() => ollama.trim() && ollama !== settings.ollamaModel && void change({ ollamaModel: ollama })}
                  className={cx(fieldClass, 'w-[180px] font-mono')}
                />
              </Row>
            )}
            {hasOllama && (
              <label className="flex min-h-11 items-start gap-3">
                <input
                  type="checkbox"
                  checked={settings.ollamaThinking}
                  onChange={(event) => void change({ ollamaThinking: event.target.checked })}
                  className="mt-0.5 size-5 shrink-0 accent-(--accent)"
                />
                <span>
                  <span className="block font-medium">{t('ollamaThinking')}</span>
                  <span className="text-[13px] text-dim">{t('ollamaThinkingHint')}</span>
                </span>
              </label>
            )}
            {settings.providers.some((provider) => provider.id === 'Microsoft Azure') && (
              <Row title={t('azureRegion')} hint={t('azureRegionHint')} htmlFor="azure-region">
                <input
                  id="azure-region"
                  value={region}
                  onChange={(event) => setRegion(event.target.value)}
                  onBlur={() => region.trim() !== settings.azureRegion && void change({ azureRegion: region })}
                  className={cx(fieldClass, 'w-[180px] font-mono')}
                />
              </Row>
            )}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="ai-context" className="font-medium">
                {t('aiContext')}
              </label>
              <span className="text-[13px] text-dim">{t('aiContextHint')}</span>
              <textarea
                id="ai-context"
                rows={2}
                value={context}
                onChange={(event) => setContext(event.target.value)}
                onBlur={() => context !== settings.context && void change({ context })}
                className={cx(fieldClass, 'mt-1 resize-y py-2.5')}
              />
            </div>
          </Section>

          <Section id="data" title={t('dataSection')}>
            <Row title={t('backupTitle')} hint={state.loaded ? t('backupHint') : t('backupNeedsFile')}>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!state.loaded} onClick={() => void exportBackup('json')}>
                  {t('exportJson')}
                </Button>
                <Button disabled={!state.loaded} onClick={() => void exportBackup('csv')}>
                  {t('exportCsv')}
                </Button>
                <Button disabled={!state.loaded || state.translating} onClick={() => void importBackup()}>
                  {t('import')}
                </Button>
              </div>
            </Row>
            <Row title={t('presetsTitle')} hint={t('presetsCount', { n: presetCount })}>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!presetCount} onClick={() => void exportPresets()}>
                  {t('exportPresets')}
                </Button>
                <Button onClick={() => void importPresets()}>{t('importPresets')}</Button>
              </div>
            </Row>
          </Section>

          <Section id="updates" title={t('updates')}>
            <Row title={t('versionLabel', { v: update.current })} hint={updateLine}>
              <div className="flex flex-wrap gap-2">
                {update.available && (
                  <Button variant="primary" onClick={onOpenUpdate}>
                    {t('seeAndUpdate')}
                  </Button>
                )}
                <Button disabled={checking} onClick={() => void api('/api/update/check', 'POST').then(refresh, fail)}>
                  {t(checking ? 'checking' : 'checkNow')}
                </Button>
              </div>
            </Row>
            <label className="flex min-h-11 items-center gap-3">
              <input type="checkbox" checked={settings.autoUpdate} onChange={(event) => void change({ autoUpdate: event.target.checked })} className="size-5 accent-(--accent)" />
              <span>{t('autoCheck')}</span>
            </label>
          </Section>

          <Section id="feedback" title={t('feedback')}>
            <Row title={t('feedbackHint')}>
              {!feedbackOpen && (
                <Button variant="chip" className="bg-raised" onClick={() => setFeedbackOpen(true)}>
                  <MessageSquare aria-hidden="true" size={16} />
                  {t('sendFeedback')}
                </Button>
              )}
            </Row>
            {feedbackOpen && (
              <form
                className="flex flex-col gap-2.5"
                onSubmit={(event) => {
                  event.preventDefault()
                  void sendFeedback()
                }}
              >
                <textarea
                  autoFocus
                  rows={5}
                  maxLength={FEEDBACK_MAX}
                  aria-label={t('sendFeedback')}
                  placeholder={t('feedbackPlaceholder')}
                  value={feedback}
                  onChange={(event) => setFeedback(event.target.value)}
                  className={cx(fieldClass, 'resize-y py-3 text-[15px]')}
                />
                <p className="m-0 text-[13px] text-dim">{t('feedbackSends', { v: update.current })}</p>
                <div className="flex flex-wrap items-center gap-2.5">
                  <Button type="submit" variant="primary" disabled={sending || feedbackLength < FEEDBACK_MIN}>
                    {t(sending ? 'sending' : 'send')}
                  </Button>
                  <Button onClick={() => setFeedbackOpen(false)}>{t('cancel')}</Button>
                  <span className="ml-auto font-mono text-xs text-dim">
                    {feedbackLength} / {FEEDBACK_MAX}
                  </span>
                </div>
              </form>
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}
