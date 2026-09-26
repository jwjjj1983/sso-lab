import { useState } from 'react'
import { ACTOR_LABELS, type Header, type TraceEvent } from '../lib/trace'

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
} as const

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

export function TraceTimeline({ events }: { events: TraceEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border p-6 text-center text-muted">
        No requests yet. Run a diagnostic and every hop will appear here as it happens.
      </p>
    )
  }
  return (
    <ol className="space-y-2" aria-label="Trace">
      {events.map((event, index) => (
        <TraceRow key={event.id} event={event} index={index + 1} />
      ))}
    </ol>
  )
}

function TraceRow({ event, index }: { event: TraceEvent; index: number }) {
  const [open, setOpen] = useState(false)
  const channel = CHANNEL_STYLES[event.channel]
  const status = event.response?.status
  const detailsId = `trace-${event.id}`

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
          {channel.label}
        </span>
        <span className="text-sm font-medium">
          {ACTOR_LABELS[event.source]} → {ACTOR_LABELS[event.target]}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          <span className="font-semibold">{event.request.method}</span>{' '}
          {shortUrl(event.request.url)}
        </span>
        <span className={`font-mono text-xs font-semibold ${statusClass(status)}`}>
          {status ?? '—'}
        </span>
        {event.duration_ms !== null && (
          <span className="font-mono text-xs text-muted">{event.duration_ms} ms</span>
        )}
      </button>
      {open && (
        <div id={detailsId} className="grid gap-3 border-t border-border p-3 lg:grid-cols-2">
          <MessagePanel
            title="Request"
            firstLine={`${event.request.method} ${event.request.url}`}
            headers={event.request.headers}
            body={event.request.body}
          />
          {event.response && (
            <MessagePanel
              title="Response"
              firstLine={`HTTP ${event.response.status}`}
              headers={event.response.headers}
              body={event.response.body}
            />
          )}
        </div>
      )}
    </li>
  )
}

function MessagePanel(props: {
  title: string
  firstLine: string
  headers: Header[]
  body: string | null
}) {
  return (
    <section className="min-w-0">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
        {props.title}
      </h3>
      <pre className="overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">
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
