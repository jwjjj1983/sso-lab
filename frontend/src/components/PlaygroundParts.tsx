import type { ReactNode } from 'react'
import type { StageStatus } from '../lib/playground'

// Building blocks shared by the protocol playgrounds.

export function Stage({ n, title, status, children }: { n: number; title: string; status: StageStatus; children: ReactNode }) {
  return (
    <section
      aria-labelledby={`stage-${n}`}
      className={`space-y-3 rounded-lg border bg-surface p-4 ${status === 'current' ? 'border-accent' : 'border-border'} ${
        status === 'todo' ? 'opacity-70' : ''
      }`}
    >
      <h3 id={`stage-${n}`} className="flex items-center gap-2 font-semibold">
        <span
          className={`flex size-6 items-center justify-center rounded-full text-xs ${
            status === 'done' ? 'bg-ok text-surface' : status === 'current' ? 'bg-accent text-accent-fg' : 'bg-surface-2 text-muted'
          }`}
          aria-hidden
        >
          {status === 'done' ? '✓' : n}
        </span>
        {title}
        {status === 'done' && <span className="sr-only">(done)</span>}
      </h3>
      <div className="space-y-3 text-sm">{children}</div>
    </section>
  )
}

export function Button({
  children,
  onClick,
  disabled,
  secondary,
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  secondary?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-2 text-sm font-medium disabled:opacity-40 ${
        secondary ? 'border border-border' : 'bg-accent text-accent-fg'
      }`}
    >
      {children}
    </button>
  )
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
}

export function Values({ values }: { values: Record<string, string> }) {
  return (
    <dl className="space-y-1 text-xs">
      {Object.entries(values).map(([name, value]) => (
        <div key={name} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2">
          <dt className="font-mono text-muted">{name}</dt>
          <dd className="font-mono break-all">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
