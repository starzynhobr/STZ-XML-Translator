import { useEffect, useRef, useState } from 'react'
import { openExternal } from '@/lib/files'
import { useT } from '@/lib/i18n'
import logo from '@/assets/stz-labs.png'
import mark from '@/assets/stz-mark.svg'
import { Button } from './ui'

const SITE = 'https://stzlabs.com'
const GITHUB = 'https://github.com/starzynhobr/STZ-XML-Translator'
const DISCORD = 'https://discord.com/invite/cTsJhtMzSe'
// App locale -> site locale; anything else falls back to English.
const SITE_LOCALES: Record<string, string> = { pt_BR: 'pt', en_US: 'en', es_ES: 'es', fr_FR: 'fr' }

/** Header pill that opens a card with the STZ Labs site, the repository and the Discord. */
export default function StzLabsBadge({ version, locale }: { version: string; locale: string }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const visit = (url: string) => { setOpen(false); void openExternal(url) }
  const page = `${SITE}/${SITE_LOCALES[locale] ?? 'en'}/projects/stz-xml-translator`

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
        className="flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-raised px-3 text-[13px] font-semibold text-ink hover:border-edge"
      >
        <img src={mark} alt="STZ" className="h-3.5" />
        Labs
      </button>
      {open && (
        <div role="dialog" aria-label="STZ Labs"
          className="absolute left-1/2 top-[calc(100%+8px)] z-50 w-[380px] -translate-x-1/2 overflow-hidden rounded-[14px] border border-edge bg-ground text-left shadow-2xl">
          <div className="flex flex-col gap-1.5 bg-gradient-to-b from-[#ff7a1a]/10 to-transparent px-[18px] py-4">
            {/* The logo's "STZ" is white: a dark tile keeps it readable in light themes too. */}
            <div className="mb-1 w-fit rounded-[10px] bg-black px-3 py-2">
              <img src={logo} alt="STZ Labs" className="h-10" />
            </div>
            <p className="m-0 text-[13px] text-dim">{t('stzLabsBy', { version })}</p>
            <p className="m-0 text-[13px]">{t('stzLabsAbout')}</p>
            <div className="mt-2 flex gap-2">
              <Button className="min-w-0 flex-1 px-3 border-transparent bg-[#ff7a1a] text-black hover:bg-[#ff8f3d]" onClick={() => visit(page)}>
                {t('stzLabsVisit')}
              </Button>
              <Button className="px-3" onClick={() => visit(GITHUB)}>GitHub</Button>
              <Button className="px-3" onClick={() => visit(DISCORD)}>Discord</Button>
            </div>
          </div>
          <p className="m-0 border-t border-line px-[18px] py-3 text-[13px] text-dim">{t('stzLabsInvite')}</p>
        </div>
      )}
    </div>
  )
}
