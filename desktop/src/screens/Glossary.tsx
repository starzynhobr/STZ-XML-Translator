import FloatingPanel from '@/components/FloatingPanel'
import { ArrowRight, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button, IconButton, PageHeader, cardClass, cx, eyebrowClass, fieldClass } from '@/components/ui'
import { api, type Term } from '@/lib/bridge'
import { JSON_FILTER, pickFile, pickSavePath } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'

interface Props {
  floating?: boolean
  terms: Term[]
  /** Display name of the target language this glossary belongs to. */
  language: string
  onChange: (terms: Term[]) => void
  onBack: () => void
}

const ROW = 'grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] items-center gap-4'

export default function Glossary({ floating = false, terms, language, onChange, onBack }: Props) {
  const t = useT()
  const [original, setOriginal] = useState('')
  const [translation, setTranslation] = useState('')

  const save = async (next: Term[]) => {
    try {
      const saved = await api<{ terms: Term[] }>('/api/glossary', 'PUT', { terms: next })
      onChange(saved.terms)
    } catch (error) {
      toast.error(errorText(t, error))
    }
  }

  const add = () => {
    const term = { original: original.trim(), translation: translation.trim() }
    if (!term.original || !term.translation) return
    setOriginal('')
    setTranslation('')
    // Adding a term that already exists replaces its translation.
    void save([term, ...terms.filter((item) => item.original !== term.original)])
  }

  // The glossary file is a plain {"original": "translation"} JSON object.
  const exportFile = async () => {
    const path = await pickSavePath('glossary.json', JSON_FILTER)
    if (!path) return
    await api('/api/glossary/export', 'POST', { path }).then(
      () => toast.success(t('toastBackup')),
      (error) => toast.error(errorText(t, error)),
    )
  }

  const importFile = async () => {
    const path = await pickFile(JSON_FILTER)
    if (!path) return
    await api<{ terms: Term[] }>('/api/glossary/import', 'POST', { path }).then(
      (data) => onChange(data.terms),
      (error) => toast.error(errorText(t, error)),
    )
  }

  const content = (
    <div className="flex min-h-full flex-col">
      {floating ? <header className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <h1 className="m-0 text-xl font-semibold">{t('glossary')}</h1>
        <span className="flex-1" />
        <Button onClick={() => void importFile()}>{t('import')}</Button>
        <Button onClick={() => void exportFile()} disabled={!terms.length}>{t('export')}</Button>
        <IconButton label={t('close')} onClick={onBack}><X aria-hidden="true" size={18} /></IconButton>
      </header> : <PageHeader title={t('glossary')} onBack={onBack} backLabel={t('backToBench')}>
        <Button onClick={() => void importFile()}>{t('import')}</Button>
        <Button onClick={() => void exportFile()} disabled={!terms.length}>
          {t('export')}
        </Button>
      </PageHeader>}

      <div className={cx('mx-auto flex w-full max-w-[920px] flex-1 flex-col gap-5 px-5', floating ? 'py-5' : 'pb-12 pt-8')}>
        <p className="m-0 max-w-[640px] text-[15px] text-dim">{t('glossaryIntro', { lang: language })}</p>

        <form
          className={cx(cardClass, 'flex flex-wrap items-end gap-3 p-[18px]')}
          onSubmit={(event) => {
            event.preventDefault()
            add()
          }}
        >
          <div className="flex flex-[1_1_200px] flex-col gap-1.5">
            <label htmlFor="term" className="text-xs text-dim">
              {t('term')}
            </label>
            <input id="term" value={original} onChange={(event) => setOriginal(event.target.value)} placeholder={t('termPlaceholder')} className={cx(fieldClass, 'text-[15px]')} />
          </div>
          <ArrowRight aria-hidden="true" size={18} className="mb-[13px] shrink-0 text-faint" />
          <div className="flex flex-[1_1_200px] flex-col gap-1.5">
            <label htmlFor="fixed" className="text-xs text-dim">
              {t('becomes')}
            </label>
            <input id="fixed" value={translation} onChange={(event) => setTranslation(event.target.value)} placeholder={t('becomesPlaceholder')} className={cx(fieldClass, 'text-[15px]')} />
          </div>
          <Button type="submit" variant="primary" disabled={!original.trim() || !translation.trim()}>
            {t('addTerm')}
          </Button>
        </form>

        <section aria-label={t('glossary')} className={cx(cardClass, 'overflow-auto', floating && 'max-h-[min(320px,40vh)]')}>
          <div className="min-w-[480px]">
            <div className={cx(ROW, eyebrowClass, 'border-b border-line px-4 py-3')}>
              <span>{t('colOriginal')}</span>
              <span>{t('fixedTranslation')}</span>
              <span />
            </div>
            {terms.map((term) => (
              <div key={term.original} className={cx(ROW, 'border-b border-rowline px-4 py-1.5 text-[15px] last:border-0')}>
                <span className="truncate text-soft">{term.original}</span>
                <span className="truncate font-medium">{term.translation}</span>
                <button
                  type="button"
                  aria-label={t('removeTerm', { term: term.original })}
                  title={t('removeTerm', { term: term.original })}
                  onClick={() => void save(terms.filter((item) => item.original !== term.original))}
                  className="flex size-11 items-center justify-center rounded-[10px] text-dim hover:bg-raised hover:text-ink"
                >
                  <Trash2 aria-hidden="true" size={16} />
                </button>
              </div>
            ))}
            {terms.length === 0 && (
              <div className="px-6 py-11 text-center text-dim">
                <div className="mb-1.5 text-[15px] font-medium text-ink">{t('glossaryEmptyTitle')}</div>
                <div>{t('glossaryEmptyBody')}</div>
              </div>
            )}
          </div>
        </section>

        <div className="text-[13px] text-dim">{t('termCount', { n: terms.length })}</div>
      </div>
    </div>
  )
  return floating ? <FloatingPanel label={t('glossary')} onDismiss={onBack}>{content}</FloatingPanel> : content
}
