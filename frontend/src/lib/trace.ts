// Mirrors backend/src/sso_lab/lab/models.py.

export type Actor = 'browser' | 'idp' | 'app-a' | 'app-b' | 'external'
export type Channel = 'front' | 'back'

export interface Header {
  name: string
  value: string
}

export interface HttpRequestRecord {
  method: string
  url: string
  headers: Header[]
  body: string | null
}

export interface HttpResponseRecord {
  status: number
  headers: Header[]
  body: string | null
}

export interface TraceEvent {
  id: string
  lab_session_id: string
  ts: string
  channel: Channel
  source: Actor
  target: Actor
  step: string | null
  request: HttpRequestRecord
  response: HttpResponseRecord | null
  duration_ms: number | null
  note: string | null
}

export const ACTOR_LABELS: Record<Actor, string> = {
  browser: 'Browser',
  idp: 'IdP',
  'app-a': 'App A',
  'app-b': 'App B',
  external: 'External',
}

/** Add events to a trace: ignore ones already present (the stream replays on reconnect), keep time order. */
export function mergeEvents(current: TraceEvent[], incoming: TraceEvent[]): TraceEvent[] {
  const seen = new Set(current.map((e) => e.id))
  const fresh = incoming.filter((e) => !seen.has(e.id))
  if (fresh.length === 0) return current
  return [...current, ...fresh].sort((a, b) => a.ts.localeCompare(b.ts))
}
