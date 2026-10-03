import { useEffect, useRef, type ReactNode } from 'react'
import { cx } from './ui'

/** Native modality supplies focus trapping, background inertness and focus restoration. */
export default function FloatingPanel({ label, onDismiss, dismissible = true, className, children }: {
  label: string; onDismiss: () => void; dismissible?: boolean; className?: string; children: ReactNode
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current!
    const previous = document.activeElement as HTMLElement | null
    element.showModal()
    return () => {
      element.close()
      // React removes the dialog before passive cleanup; native restoration
      // alone cannot return focus to its opener in that case.
      requestAnimationFrame(() => {
        const remaining = document.querySelector('dialog[open]')
        if (previous?.isConnected && (!remaining || remaining.contains(previous))) previous.focus()
      })
    }
  }, [])
  return (
    <dialog ref={dialog} aria-label={label}
      onCancel={(event) => { event.preventDefault(); if (dismissible) onDismiss() }}
      onClick={(event) => {
        if (!dismissible || event.target !== event.currentTarget) return
        const rect = event.currentTarget.getBoundingClientRect()
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onDismiss()
      }}
      className={cx('m-auto max-h-[calc(100dvh-48px)] w-[min(960px,calc(100vw-48px))] overflow-y-auto rounded-[18px] border border-edge bg-ground p-0 text-ink shadow-2xl backdrop:bg-black/45', className)}
    >{children}</dialog>
  )
}
