import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { Translate } from '@/lib/i18n'

type Variant = 'primary' | 'secondary' | 'chip' | 'quiet'

const BASE =
  'inline-flex min-h-11 items-center justify-center gap-2 whitespace-nowrap rounded-[10px] px-3.5 text-sm font-medium transition-colors disabled:cursor-default disabled:opacity-50'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent px-[18px] font-semibold text-on-accent enabled:hover:brightness-110',
  secondary: 'border border-edge text-ink enabled:hover:bg-raised',
  chip: 'border border-edge bg-chip text-ink enabled:hover:bg-raised',
  quiet: 'text-dim enabled:hover:text-ink',
}

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

export const buttonClass = (variant: Variant = 'secondary', extra = '') => cx(BASE, VARIANTS[variant], extra)

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export function Button({ variant = 'secondary', className, type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, className)} {...props} />
}

/** Square, icon-only button. `label` is required: there is no visible text. */
export function IconButton({ label, className, type = 'button', ...props }: ButtonProps & { label: string }) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        'flex size-11 shrink-0 items-center justify-center rounded-[10px] border border-edge text-soft transition-colors enabled:hover:bg-raised disabled:opacity-40',
        className,
      )}
      {...props}
    />
  )
}

export const fieldClass =
  'min-h-11 rounded-[10px] border border-edge-strong bg-field px-3 text-ink placeholder:text-faint'

export const cardClass = 'rounded-[14px] border border-line bg-panel'

export const eyebrowClass = 'text-xs font-medium uppercase tracking-[0.04em] text-dim'

export function LogoMark({ className = 'size-[22px]' }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cx('shrink-0 text-accent', className)}>
      <path d="M8 6 3 12l5 6" />
      <path d="M16 6l5 6-5 6" />
      <path d="M14 4l-4 16" />
    </svg>
  )
}

/** Page chrome shared by the secondary screens (settings, glossary). */
export function PageHeader({ title, onBack, backLabel, children }: { title: string; onBack: () => void; backLabel: string; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-3.5 border-b border-line px-5 py-3">
      <Button onClick={onBack} className="text-soft">
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m15 6-6 6 6 6" />
        </svg>
        {backLabel}
      </Button>
      <h1 className="m-0 text-xl font-semibold tracking-[-0.01em]">{title}</h1>
      <span className="flex-1" />
      {children}
    </header>
  )
}

/** Short display names for providers; the engine keeps the canonical ids. */
export function providerLabel(id: string, t: Translate): string {
  if (id === 'Google Translate (Free)') return `Google Translate · ${t('noKeyNeeded')}`
  if (id === 'Ollama (Local)') return 'Ollama · local'
  if (id === 'Llama 3 (Local)') return 'Llama 3 · local'
  return id
}

export const providerName = (id: string) => id.replace(/\s*\((Free|Local)\)$/, '')
