import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PageHeader, cardClass, cx, fieldClass } from '@/components/ui'
import { HELP, fold, type HelpTopic } from '@/lib/help'
import { useT } from '@/lib/i18n'
import type { MessageKey } from '@/lib/messages'

const SECTIONS: [HelpTopic['section'], MessageKey][] = [
  ['start', 'helpSectionStart'],
  ['translate', 'helpSectionTranslate'],
  ['quality', 'helpSectionQuality'],
  ['game', 'helpSectionGame'],
  ['more', 'helpSectionMore'],
]

interface Props {
  locale: string
  onBack: () => void
}

/** How to use the app: every feature in short topics, searchable, in the UI language. */
export default function Help({ locale, onBack }: Props) {
  const t = useT()
  const [query, setQuery] = useState('')
  const topics = HELP[locale] ?? HELP.en_US

  const visible = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean)
    if (!words.length) return topics
    return topics.filter((topic) => {
      const haystack = fold([topic.title, ...topic.body, topic.keywords ?? ''].join(' '))
      return words.every((word) => haystack.includes(word))
    })
  }, [topics, query])

  return (
    <div className="flex min-h-full flex-col">
      <PageHeader title={t('helpTitle')} onBack={onBack} backLabel={t('back')} />
      <div className="mx-auto flex w-full max-w-[1080px] gap-8 px-5 py-7">
        <nav aria-label={t('helpTitle')} className="sticky top-6 hidden w-[180px] shrink-0 flex-col gap-1 self-start md:flex">
          {SECTIONS.map(([section, label]) => (
            <a key={section} href={`#help-${section}`} className="rounded-[8px] px-3 py-2 text-sm text-soft hover:bg-raised hover:text-ink">
              {t(label)}
            </a>
          ))}
        </nav>
        <main className="flex min-w-0 flex-1 flex-col gap-5">
          <label className={cx(fieldClass, 'search-field flex items-center gap-2 border-edge bg-chip text-dim')}>
            <Search aria-hidden="true" size={16} className="shrink-0" />
            <input
              autoFocus
              type="search"
              aria-label={t('helpSearch')}
              placeholder={t('helpSearch')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-faint"
            />
          </label>
          {visible.length === 0 && <p className="m-0 text-dim">{t('helpEmpty')}</p>}
          {SECTIONS.map(([section, label]) => {
            const items = visible.filter((topic) => topic.section === section)
            if (!items.length) return null
            return (
              <section key={section} id={`help-${section}`} aria-labelledby={`help-${section}-title`} className="flex scroll-mt-6 flex-col gap-3">
                <h2 id={`help-${section}-title`} className="m-0 text-xs font-medium uppercase tracking-[0.04em] text-dim">{t(label)}</h2>
                {items.map((topic) => (
                  <article key={topic.id} id={`help-topic-${topic.id}`} className={cx(cardClass, 'flex flex-col gap-2 px-5 py-4')}>
                    <h3 className="m-0 text-base font-semibold">{topic.title}</h3>
                    {topic.body.map((paragraph, index) => (
                      <p key={index} className="m-0 text-sm leading-relaxed text-soft">{paragraph}</p>
                    ))}
                  </article>
                ))}
              </section>
            )
          })}
        </main>
      </div>
    </div>
  )
}
