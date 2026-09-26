import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { TraceTimeline } from '../components/TraceTimeline'
import { api, ensureSession } from '../lib/api'
import { runInPopup } from '../lib/popup'
import { useTraceStream } from '../lib/useTraceStream'

const STATUS_TEXT = {
  idle: 'Not connected',
  connecting: 'Connecting…',
  live: 'Live',
  reconnecting: 'Reconnecting…',
} as const

/**
 * Proves the lab plumbing end to end: three separate sites, both kinds of channel,
 * and the recorder streaming every hop into this page.
 */
export function DiagnosticsPage() {
  const queryClient = useQueryClient()
  const session = useQuery({ queryKey: ['lab-session'], queryFn: ensureSession })
  const { events, status } = useTraceStream(session.data?.id)
  const [message, setMessage] = useState<string | null>(null)

  const newSession = useMutation({
    mutationFn: api.createSession,
    onSuccess: (data) => queryClient.setQueryData(['lab-session'], data),
  })
  const backChannel = useMutation({
    mutationFn: api.backChannelDiagnostic,
    onSuccess: (results) =>
      setMessage(
        results.every((r) => r.status === 200)
          ? 'App A reached the IdP and App B server to server.'
          : `Some calls failed: ${results.map((r) => `${r.target}=${r.status ?? r.error}`).join(', ')}`,
      ),
    onError: (err) => setMessage(err.message),
  })
  const frontChannel = useMutation({
    mutationFn: () => runInPopup('/rp/diag/start', 'sso-lab:diag'),
    onSuccess: () => setMessage('The browser went App A → IdP → App A and reported back.'),
    onError: (err) => setMessage(err.message),
  })

  const ready = session.isSuccess
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Lab diagnostics</h1>
        <p className="max-w-2xl text-muted">
          This page checks that the lab's plumbing works. App A, the IdP and App B run as three
          separate sites. Each button sends real traffic between them, and the recorder streams
          every hop into the trace below.
        </p>
      </header>

      <section className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!ready || frontChannel.isPending}
          onClick={() => frontChannel.mutate()}
          className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg disabled:opacity-50"
        >
          Front-channel round trip
        </button>
        <button
          type="button"
          disabled={!ready || backChannel.isPending}
          onClick={() => backChannel.mutate()}
          className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg disabled:opacity-50"
        >
          Back-channel ping
        </button>
        <button
          type="button"
          disabled={newSession.isPending}
          onClick={() => newSession.mutate()}
          className="rounded-md border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
        >
          Clear trace
        </button>
        <span className="ml-auto flex items-center gap-2 text-sm text-muted" role="status">
          <span
            aria-hidden
            className={`inline-block size-2 rounded-full ${status === 'live' ? 'bg-ok' : 'bg-warn'}`}
          />
          {session.isError ? 'Could not start a lab session' : STATUS_TEXT[status]}
        </span>
      </section>

      {message && (
        <p className="rounded-md border border-border bg-surface px-3 py-2 text-sm" aria-live="polite">
          {message}
        </p>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Trace</h2>
        <TraceTimeline events={events} />
      </section>
    </div>
  )
}
