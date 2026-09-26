import { useEffect, useState } from 'react'
import { mergeEvents, type TraceEvent } from './trace'

export type StreamStatus = 'idle' | 'connecting' | 'live' | 'reconnecting'

interface StreamState {
  sessionId: string
  events: TraceEvent[]
  status: Exclude<StreamStatus, 'idle' | 'connecting'>
}

/**
 * Live trace of the current lab session, via Server-Sent Events.
 * Pass the session id so a new session (e.g. after "Clear trace") opens a fresh stream.
 */
export function useTraceStream(sessionId: string | undefined) {
  // State is tagged with the session it belongs to, so switching sessions shows an empty
  // trace immediately without resetting state inside the effect.
  const [state, setState] = useState<StreamState | null>(null)

  useEffect(() => {
    if (!sessionId) return
    const update = (fn: (s: StreamState) => StreamState) =>
      setState((prev) =>
        fn(prev?.sessionId === sessionId ? prev : { sessionId, events: [], status: 'live' }),
      )

    const source = new EventSource('/api/lab/events')
    source.onopen = () => update((s) => ({ ...s, status: 'live' }))
    // EventSource reconnects by itself; the server replays history and we de-duplicate.
    source.onerror = () => update((s) => ({ ...s, status: 'reconnecting' }))
    source.addEventListener('trace', (msg) => {
      const event = JSON.parse((msg as MessageEvent<string>).data) as TraceEvent
      update((s) => ({ ...s, events: mergeEvents(s.events, [event]) }))
    })
    return () => source.close()
  }, [sessionId])

  const current = sessionId && state?.sessionId === sessionId ? state : null
  const status: StreamStatus = !sessionId ? 'idle' : (current?.status ?? 'connecting')
  return { events: current?.events ?? [], status }
}
