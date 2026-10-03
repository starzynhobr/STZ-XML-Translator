import { ArrowRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui'
import { api, type UpdateInfo } from '@/lib/bridge'
import { quitApp } from '@/lib/files'
import { errorText, useT } from '@/lib/i18n'

type Block = { kind: 'heading'; text: string } | { kind: 'list'; items: string[] } | { kind: 'text'; text: string }

/**
 * Release notes are GitHub markdown. Only headings, bullets and paragraphs are
 * laid out; everything is rendered as text, never as HTML.
 */
function parseNotes(notes: string): Block[] {
  const blocks: Block[] = []
  const clean = (text: string) => text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`(.+?)`/g, '$1').trim()
  for (const raw of notes.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const heading = /^#{1,6}\s+(.*)$/.exec(line)
    const bullet = /^[-*]\s+(.*)$/.exec(line)
    const last = blocks[blocks.length - 1]
    if (heading) blocks.push({ kind: 'heading', text: clean(heading[1]) })
    else if (bullet && last?.kind === 'list') last.items.push(clean(bullet[1]))
    else if (bullet) blocks.push({ kind: 'list', items: [clean(bullet[1])] })
    else blocks.push({ kind: 'text', text: clean(line) })
  }
  return blocks
}

interface Props {
  update: UpdateInfo
  refresh: () => Promise<void>
  onClose: () => void
}

export default function UpdateDialog({ update, refresh, onClose }: Props) {
  const t = useT()
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
  }, [])

  const run = (action: () => Promise<unknown>) => action().then(refresh, (error) => toast.error(errorText(t, error)))
  const blocks = parseNotes(update.notes)
  const downloading = update.status === 'downloading'
  const ready = update.status === 'ready'

  return (
    <dialog
      ref={dialog}
      aria-labelledby="update-title"
      onClose={onClose}
      className="m-auto max-h-[min(700px,calc(100vh-40px))] w-[min(720px,calc(100vw-32px))] flex-col overflow-hidden rounded-[18px] border border-edge bg-panel p-0 text-ink backdrop:bg-black/60 open:flex"
    >
      <div className="flex flex-col gap-2.5 border-b border-line px-8 pb-[22px] pt-7">
        <div className="flex items-center gap-2.5 font-mono text-[13px] text-dim">
          <span>{update.current}</span>
          <ArrowRight aria-hidden="true" size={16} />
          <span className="rounded-md bg-accent px-2 py-0.5 font-medium text-on-accent">{update.version}</span>
        </div>
        <h1 id="update-title" className="m-0 text-[30px] font-semibold leading-[1.15] tracking-[-0.03em]">
          {t('whatsNew', { v: update.version })}
        </h1>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-8 py-6 text-[15px] leading-normal">
        {blocks.length === 0 && <p className="m-0 text-dim">{t('noNotes')}</p>}
        {blocks.map((block, index) =>
          block.kind === 'heading' ? (
            <h2 key={index} className="m-0 mt-2 text-xs font-semibold uppercase tracking-[0.06em] text-accent first:mt-0">
              {block.text}
            </h2>
          ) : block.kind === 'list' ? (
            <ul key={index} className="m-0 flex list-none flex-col gap-2.5 p-0">
              {block.items.map((item, at) => (
                <li key={at} className="flex gap-3 text-soft">
                  <span aria-hidden="true" className="mt-[9px] size-1.5 shrink-0 rounded-full bg-accent" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p key={index} className="m-0 text-soft">
              {block.text}
            </p>
          ),
        )}
        <p className="m-0 mt-2 rounded-xl bg-ground px-4 py-3.5 text-[13px] text-dim">{t('updateSafety')}</p>
        {update.status === 'error' && <p className="m-0 text-[13px] text-bad">{t('updateError')}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2.5 border-t border-line px-8 py-[18px]">
        <Button
          variant="quiet"
          disabled={downloading}
          onClick={() => {
            void run(() => api('/api/update/skip', 'POST'))
            dialog.current?.close()
          }}
        >
          {t('skipVersion')}
        </Button>
        <span className="flex-1" />
        <Button onClick={() => dialog.current?.close()}>{t('later')}</Button>
        {ready ? (
          <Button
            variant="primary"
            className="px-5"
            onClick={() =>
              void run(async () => {
                await api('/api/update/install', 'POST')
                await quitApp()
              })
            }
          >
            {t('installRestart')}
          </Button>
        ) : (
          <Button variant="primary" className="px-5" disabled={downloading} onClick={() => void run(() => api('/api/update/download', 'POST'))}>
            {downloading ? t('downloading', { p: update.progress }) : t('downloadInstall')}
          </Button>
        )}
      </div>
    </dialog>
  )
}
