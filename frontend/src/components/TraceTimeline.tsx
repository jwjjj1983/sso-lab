import { useState } from 'react'
import { ACTOR_LABELS, type Check, type Header, type TraceEvent } from '../lib/trace'

const CHANNEL_STYLES = {
  front: {
    label: 'Front channel',
    hint: 'Carried by the browser: visible in the address bar, history and dev tools.',
    className: 'bg-front-bg text-front',
  },
  back: {
    label: 'Back channel',
    hint: 'Server to server: the browser never sees this request.',
    className: 'bg-back-bg text-back',
  },
  local: {
    label: 'Inside',
    hint: 'Work done inside one party; no message was sent.',
    className: 'bg-surface-2 text-muted',
  },
} as const

export interface StepRef {
  id: string
  number: number
  title: string
}

interface Props {
  events: TraceEvent[]
  /** Map a trace step id to the diagram step it belongs to, if any. */
  stepRef?: (id: string) => StepRef | undefined
  onSelectStep?: (id: string) => void
  emptyText?: string
}

function statusClass(status: number | undefined): string {
  if (status === undefined) return 'text-muted'
  if (status >= 400) return 'text-err'
  if (status >= 300) return 'text-warn'
  return 'text-ok'
}

function shortUrl(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.pathname + parsed.search
  } catch {
    return url
  }
}

export function TraceTimeline({ events, stepRef, onSelectStep, emptyText }: Props) {
  if (events.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border p-6 text-center text-muted">
        {emptyText ?? 'No requests yet. Run a diagnostic and every hop will appear here as it happens.'}
      </p>
    )
  }
  return (
    <ol className="space-y-2" aria-label="Trace">
      {events.map((event, index) => (
        <TraceRow
          key={event.id}
          event={event}
          index={index + 1}
          stepRef={stepRef}
          onSelectStep={onSelectStep}
        />
      ))}
    </ol>
  )
}

function TraceRow({
  event,
  index,
  stepRef,
  onSelectStep,
}: {
  event: TraceEvent
  index: number
  stepRef?: Props['stepRef']
  onSelectStep?: Props['onSelectStep']
}) {
  const [open, setOpen] = useState(false)
  const channel = CHANNEL_STYLES[event.channel]
  const status = event.response?.status
  const detailsId = `trace-${event.id}`
  const steps = [event.step, event.response_step]
    .filter((s): s is string => !!s)
    .map((s) => stepRef?.(s))
    .filter((s): s is StepRef => !!s)

  return (
    <li className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={detailsId}
        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left"
      >
        <span className="w-6 text-right font-mono text-xs text-muted">{index}</span>
        <span
          title={channel.hint}
          className={`rounded px-1.5 py-0.5 text-xs font-semibold ${channel.className}`}
        >
          {event.channel === 'local' ? `Inside ${ACTOR_LABELS[event.source]}` : channel.label}
        </span>
        {event.request ? (
          <>
            <span className="text-sm font-medium">
              {ACTOR_LABELS[event.source]} → {ACTOR_LABELS[event.target]}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-xs">
              <span className="font-semibold">{event.request.method}</span> {shortUrl(event.request.url)}
            </span>
            <span className={`font-mono text-xs font-semibold ${statusClass(status)}`}>{status ?? '—'}</span>
            {event.duration_ms !== null && (
              <span className="font-mono text-xs text-muted">{event.duration_ms} ms</span>
            )}
          </>
        ) : (
          <span className="min-w-0 flex-1 text-sm">
            {event.note}
            {event.checks.length > 0 && (
              <span className={`ml-2 text-xs font-semibold ${event.checks.every((c) => c.ok) ? 'text-ok' : 'text-err'}`}>
                {event.checks.filter((c) => c.ok).length}/{event.checks.length} checks passed
              </span>
            )}
          </span>
        )}
      </button>

      {(steps.length > 0 || (event.request && event.note)) && (
        <div className="flex flex-wrap items-center gap-2 px-3 pb-2 pl-12 text-xs">
          {steps.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelectStep?.(s.id)}
              className="rounded-full border border-border px-2 py-0.5 text-muted hover:border-accent hover:text-accent"
            >
              Step {s.number}: {s.title}
            </button>
          ))}
          {event.request && event.note && <span className="font-medium text-accent">{event.note}</span>}
        </div>
      )}

      {open && (
        <div id={detailsId} className="grid gap-3 border-t border-border p-3 lg:grid-cols-2">
          {event.request && (
            <MessagePanel
              title="Request"
              firstLine={`${event.request.method} ${event.request.url}`}
              headers={event.request.headers}
              body={event.request.body}
            />
          )}
          {event.response && (
            <MessagePanel
              title="Response"
              firstLine={`HTTP ${event.response.status}`}
              headers={event.response.headers}
              body={event.response.body}
            />
          )}
          {event.checks.length > 0 && <Checks checks={event.checks} />}
          {Object.keys(event.data).length > 0 && (
            <section className="min-w-0 space-y-2">
              <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Values</h3>
              {Object.entries(event.data).map(([name, value]) => (
                <div key={name}>
                  <p className="font-mono text-xs text-accent">{name}</p>
                  <pre className="overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs whitespace-pre-wrap break-all">
                    {value}
                  </pre>
                </div>
              ))}
            </section>
          )}
        </div>
      )}
    </li>
  )
}

export function Checks({ checks }: { checks: Check[] }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Checks</h3>
      <ul className="space-y-1 text-sm">
        {checks.map((c) => (
          <li key={c.label} className="flex gap-2">
            <span aria-hidden className={c.ok ? 'text-ok' : 'text-err'}>
              {c.ok ? '✓' : '✗'}
            </span>
            <span className="sr-only">{c.ok ? 'Passed:' : 'Failed:'}</span>
            <span className="min-w-0">
              {c.label}
              {c.detail && <span className="block font-mono text-xs break-all text-muted">{c.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function MessagePanel(props: { title: string; firstLine: string; headers: Header[]; body: string | null }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">{props.title}</h3>
      <pre className="overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs leading-relaxed break-all whitespace-pre-wrap">
        <span className="font-semibold">{props.firstLine}</span>
        {'\n'}
        {props.headers.map((h, i) => (
          <span key={i}>
            <span className="text-accent">{h.name}</span>: {h.value}
            {'\n'}
          </span>
        ))}
        {props.body && `\n${props.body}`}
      </pre>
    </section>
  )
}
