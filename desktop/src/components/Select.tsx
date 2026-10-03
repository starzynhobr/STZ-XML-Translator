import { Check, ChevronDown } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { cx, fieldClass } from './ui'

interface Props {
  id?: string
  name?: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/** A themed, keyboard-accessible select. The native popover escapes dialog clipping. */
export default function Select({ id, name, value, options, onChange, disabled, className, 'aria-label': label }: Props) {
  const generated = useId()
  const controlId = id ?? generated
  const listId = `${controlId}-options`
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const typed = useRef({ text: '', at: 0 })
  const selected = Math.max(0, options.findIndex((option) => option.value === value))

  const close = () => setOpen(false)
  const choose = (index: number) => {
    const option = options[index]
    if (option) onChange(option.value)
    close()
    button.current?.focus()
  }

  useEffect(() => {
    if (!open || disabled) return
    const menu = list.current!
    const trigger = button.current!
    const measure = document.createElement('canvas').getContext('2d')!
    measure.font = getComputedStyle(menu).font
    const contentWidth = Math.max(0, ...options.map((option) => measure.measureText(option.label).width)) + 64
    const position = () => {
      const rect = trigger.getBoundingClientRect()
      const height = Math.min(300, options.length * 40 + 12, window.innerHeight - 24)
      const below = window.innerHeight - rect.bottom - 12
      const above = rect.top - 12
      const up = below < height && above > below
      menu.style.maxHeight = `${Math.max(40, Math.min(height, up ? above : below))}px`
      menu.style.width = `${Math.min(Math.max(rect.width, 260, contentWidth), window.innerWidth - 24)}px`
      menu.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - parseFloat(menu.style.width) - 12))}px`
      menu.style.top = `${up ? rect.top - Math.min(height, above) - 6 : rect.bottom + 6}px`
    }
    menu.showPopover()
    position()
    const outside = (event: PointerEvent) => {
      if (!menu.contains(event.target as Node) && !trigger.contains(event.target as Node)) close()
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => {
      menu.hidePopover()
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', position)
      window.removeEventListener('scroll', position, true)
    }
  }, [open, disabled, options.length])

  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [active, open])

  return (
    <span className={cx('inline-flex min-w-0', className)}>
      <button
        ref={button} id={controlId} name={name} type="button" role="combobox"
        aria-label={label} aria-haspopup="listbox" aria-expanded={open}
        aria-controls={listId} aria-activedescendant={open ? `${listId}-${active}` : undefined}
        disabled={disabled}
        className={cx(fieldClass, 'flex w-full items-center justify-between gap-3 text-left disabled:cursor-default disabled:opacity-50')}
        onClick={() => { setActive(selected); setOpen(!open) }}
        onBlur={(event) => { if (!list.current?.contains(event.relatedTarget as Node)) close() }}
        onKeyDown={(event) => {
          if (event.key === 'Tab') { close(); return }
          if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); return }
          if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault()
            setOpen(true)
            setActive(event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : !open ? selected : Math.max(0, Math.min(options.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1))))
          } else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            if (open) choose(active)
            else { setActive(selected); setOpen(true) }
          } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
            const now = Date.now()
            typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : '') + event.key.toLocaleLowerCase(), at: now }
            const match = options.findIndex((option) => option.label.toLocaleLowerCase().startsWith(typed.current.text))
            if (match >= 0) { event.preventDefault(); setActive(match); setOpen(true) }
          }
        }}
      >
        <span className="min-w-0 truncate" title={options[selected]?.label}>{options[selected]?.label}</span>
        <ChevronDown aria-hidden="true" size={16} className="shrink-0 text-dim" />
      </button>
      <div ref={list} id={listId} role="listbox" aria-label={label} popover="manual" className="themed-options rounded-[12px] border border-edge bg-panel p-1.5 text-sm text-ink shadow-2xl">
        {options.map((option, index) => (
          <div
            key={option.value} id={`${listId}-${index}`} role="option" aria-selected={option.value === value}
            onPointerDown={(event) => event.preventDefault()}
            onPointerMove={() => setActive(index)} onClick={(event) => { event.preventDefault(); choose(index) }}
            className={cx('flex min-h-10 cursor-pointer items-center gap-2 rounded-[7px] px-2.5', index === active && 'bg-raised', option.value === value && 'font-medium text-accent')}
          >
            <span className="min-w-0 flex-1 truncate" title={option.label}>{option.label}</span>
            {option.value === value && <Check aria-hidden="true" size={15} className="shrink-0" />}
          </div>
        ))}
      </div>
    </span>
  )
}
