import { useCallback, useEffect, useRef, useState } from 'react'
import { toast, Toaster } from 'sonner'
import UpdateDialog from '@/components/UpdateDialog'
import { Button, LogoMark } from '@/components/ui'
import { api, retryEngine, useEngine, type EngineStatus, type Term, type Theme } from '@/lib/bridge'
import { I18nProvider, useT } from '@/lib/i18n'
import { HTML_LANG } from '@/lib/messages'
import Bench from '@/screens/Bench'
import Glossary from '@/screens/Glossary'
import { ProjectView, ProjectsHome } from '@/screens/Projects'
import Settings from '@/screens/Settings'
import Start from '@/screens/Start'

type Screen = 'main' | 'start' | 'settings'

const systemTheme = () => (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')

/** Applies theme and accent to <html>; "system" follows the OS as it changes. */
function useAppearance(theme: Theme | undefined, accent: string | undefined, locale: string | undefined) {
  const [resolved, setResolved] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    if (!theme) return
    const apply = () => setResolved(theme === 'system' ? systemTheme() : theme)
    apply()
    if (theme !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: light)')
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = resolved
    if (accent) root.dataset.accent = accent
    if (locale) root.lang = HTML_LANG[locale] ?? 'en'
  }, [resolved, accent, locale])

  return resolved
}

function Waiting({ offline, status, onRetry }: { offline: boolean; status: EngineStatus | null; onRetry: () => void }) {
  const t = useT()
  const failed = status?.phase === 'failed'
  return (
    <div role={failed ? 'alert' : 'status'} className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center text-dim">
      <LogoMark className="size-9" />
      <p className="m-0">{t(failed ? 'engineFailed' : offline ? 'offline' : 'connecting')}</p>
      {failed && <>
        <p className="m-0 max-w-lg">{t(status.reason === 'missing' ? 'engineMissing' : status.reason === 'timeout' ? 'engineTimeout' : 'engineFailureHint')}</p>
        <Button variant="primary" onClick={onRetry}>{t('retryEngine')}</Button>
        <p className="m-0 max-w-2xl break-all text-xs">{t('engineLog')}: {status.logPath}</p>
      </>}
    </div>
  )
}

function RecoveryNotice({ status }: { status: EngineStatus | null }) {
  const t = useT()
  const announced = useRef(0)
  useEffect(() => {
    if (status?.phase === 'ready' && status.generation > 1 && status.generation !== announced.current) {
      announced.current = status.generation
      toast.info(t('engineRecovered'), { duration: 10_000 })
    }
  }, [status, t])
  return null
}

export default function App() {
  const { state, entries, online, engineStatus, refresh } = useEngine()
  const [screen, setScreen] = useState<Screen>('main')
  // Picking fields for a file: '' opens the file chooser, a path opens that file.
  const [picking, setPicking] = useState<string | null>(null)
  const [glossaryOpen, setGlossaryOpen] = useState(false)
  const [terms, setTerms] = useState<Term[]>([])
  const [updateOpen, setUpdateOpen] = useState(false)
  const [announced, setAnnounced] = useState('')
  const settings = state?.settings
  const theme = useAppearance(settings?.theme, settings?.accent, settings?.locale)

  const loadTerms = useCallback(() => {
    void api<{ terms: Term[] }>('/api/glossary').then(
      (data) => setTerms(data.terms),
      () => undefined,
    )
  }, [])

  // Each target language has its own glossary: reload when the target changes.
  const ready = state !== null
  const target = settings?.target
  useEffect(() => {
    if (ready) loadTerms()
  }, [ready, target, loadTerms])

  // A new version shows its notes once per launch; after that it waits in the footer.
  const update = state?.update
  useEffect(() => {
    if (update?.available && update.version !== announced) {
      setAnnounced(update.version)
      setUpdateOpen(true)
    }
  }, [update?.available, update?.version, announced])

  const openUpdate = () => setUpdateOpen(true)

  let content
  if (!state || !online) {
    content = <Waiting offline={!online} status={engineStatus} onRetry={() => { void retryEngine().then(refresh) }} />
  } else if (screen === 'settings') {
    content = <Settings state={state} refresh={refresh} onBack={() => setScreen('main')} onOpenUpdate={openUpdate} />
  } else if (!state.loaded && picking !== null) {
    content = (
      <Start
        key={picking}
        initialPath={picking || undefined}
        state={state}
        refresh={refresh}
        onLoaded={() => { setPicking(null); setScreen('main') }}
        onBack={() => setPicking(null)}
        onOpenSettings={() => setScreen('settings')}
        onOpenGlossary={() => setGlossaryOpen(true)}
      />
    )
  } else if (!state.loaded && state.project) {
    content = (
      <ProjectView
        state={state}
        refresh={refresh}
        onPickFile={setPicking}
        onOpenSettings={() => setScreen('settings')}
        onOpenGlossary={() => setGlossaryOpen(true)}
      />
    )
  } else if (!state.loaded) {
    content = (
      <ProjectsHome
        state={state}
        refresh={refresh}
        onOpenXml={() => setPicking('')}
        onOpenSettings={() => setScreen('settings')}
        onOpenGlossary={() => setGlossaryOpen(true)}
      />
    )
  } else {
    content = (
      <Bench
        state={state}
        entries={entries}
        terms={terms}
        refresh={refresh}
        onOpenStart={() => setScreen('start')}
        onOpenSettings={() => setScreen('settings')}
        onOpenGlossary={() => setGlossaryOpen(true)}
        onOpenUpdate={openUpdate}
      />
    )
  }

  return (
    <I18nProvider locale={settings?.locale ?? 'pt_BR'}>
      <RecoveryNotice status={engineStatus} />
      <div className="h-full overflow-y-auto">{content}</div>
      {state && online && screen === 'start' && state.loaded && <Start
        floating state={state} refresh={refresh}
        onLoaded={() => setScreen('main')} onBack={() => setScreen('main')}
        onOpenSettings={() => setScreen('settings')} onOpenGlossary={() => setGlossaryOpen(true)}
      />}
      {state && online && glossaryOpen && <Glossary
        floating terms={terms}
        language={Object.entries(state.settings.targets).find(([, code]) => code === state.settings.target)?.[0] ?? state.settings.target}
        onChange={(next) => { setTerms(next); void refresh() }}
        onBack={() => setGlossaryOpen(false)}
      />}
      {state && updateOpen && state.update.available && (
        <UpdateDialog update={state.update} refresh={refresh} onClose={() => setUpdateOpen(false)} />
      )}
      <Toaster theme={theme} position="bottom-center" toastOptions={{ style: { fontFamily: 'inherit' } }} />
    </I18nProvider>
  )
}
