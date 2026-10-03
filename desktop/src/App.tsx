import { useCallback, useEffect, useState } from 'react'
import { Toaster } from 'sonner'
import UpdateDialog from '@/components/UpdateDialog'
import { LogoMark } from '@/components/ui'
import { api, useEngine, type Term, type Theme } from '@/lib/bridge'
import { I18nProvider, useT } from '@/lib/i18n'
import { HTML_LANG } from '@/lib/messages'
import Bench from '@/screens/Bench'
import Glossary from '@/screens/Glossary'
import Settings from '@/screens/Settings'
import Start from '@/screens/Start'

type Screen = 'main' | 'start' | 'settings' | 'glossary'

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

function Waiting({ offline }: { offline: boolean }) {
  const t = useT()
  return (
    <div role="status" className="flex h-full flex-col items-center justify-center gap-4 text-dim">
      <LogoMark className="size-9" />
      <p className="m-0">{t(offline ? 'offline' : 'connecting')}</p>
    </div>
  )
}

export default function App() {
  const { state, entries, online, refresh } = useEngine()
  const [screen, setScreen] = useState<Screen>('main')
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
  if (!state) {
    content = <Waiting offline={!online} />
  } else if (screen === 'settings') {
    content = <Settings state={state} refresh={refresh} onBack={() => setScreen('main')} onOpenUpdate={openUpdate} />
  } else if (screen === 'glossary') {
    content = (
      <Glossary
        terms={terms}
        language={Object.entries(state.settings.targets).find(([, code]) => code === state.settings.target)?.[0] ?? state.settings.target}
        onChange={(next) => {
          setTerms(next)
          void refresh()
        }}
        onBack={() => setScreen('main')}
      />
    )
  } else if (screen === 'start' || !state.loaded) {
    content = (
      <Start
        state={state}
        refresh={refresh}
        onLoaded={() => setScreen('main')}
        onBack={state.loaded ? () => setScreen('main') : null}
        onOpenSettings={() => setScreen('settings')}
        onOpenGlossary={() => setScreen('glossary')}
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
        onOpenGlossary={() => setScreen('glossary')}
        onOpenUpdate={openUpdate}
      />
    )
  }

  return (
    <I18nProvider locale={settings?.locale ?? 'pt_BR'}>
      <div className="h-full overflow-y-auto">{content}</div>
      {state && updateOpen && state.update.available && (
        <UpdateDialog update={state.update} refresh={refresh} onClose={() => setUpdateOpen(false)} />
      )}
      <Toaster theme={theme} position="bottom-center" toastOptions={{ style: { fontFamily: 'inherit' } }} />
    </I18nProvider>
  )
}
