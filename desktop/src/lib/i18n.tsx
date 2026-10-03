import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { EngineError } from './bridge'
import { MESSAGES, type MessageKey } from './messages'

export type Translate = (key: MessageKey, values?: Record<string, string | number>) => string

const I18nContext = createContext<Translate>((key) => key)

export function I18nProvider({ locale, children }: { locale: string; children: ReactNode }) {
  const t = useMemo<Translate>(() => {
    const messages = MESSAGES[locale] ?? MESSAGES.en_US
    return (key, values) => {
      const template = messages[key] ?? MESSAGES.en_US[key] ?? key
      if (!values) return template
      return template.replace(/\{(\w+)\}/g, (match, name) =>
        name in values ? String(values[name]) : match,
      )
    }
  }, [locale])
  return <I18nContext.Provider value={t}>{children}</I18nContext.Provider>
}

export const useT = () => useContext(I18nContext)

/** The user-facing sentence for a refusal from the engine. */
export function errorText(t: Translate, error: unknown): string {
  const code = error instanceof EngineError ? error.code : 'unknown'
  const key = `error.${code}` as MessageKey
  return key in MESSAGES.en_US ? t(key) : t('error.unknown')
}
