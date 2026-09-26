// Mirrors backend/src/sso_lab/lab/models.py.

export type Actor = 'browser' | 'idp' | 'app-a' | 'app-b' | 'external'
export type Channel = 'front' | 'back' | 'local'

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

export interface Check {
  label: string
  ok: boolean
  detail: string | null
}

export interface TraceEvent {
  id: string
  lab_session_id: string
  ts: string
  channel: Channel
  source: Actor
  target: Actor
  step: string | null
  /** Set when the response belongs to a different protocol step than the request. */
  response_step: string | null
  /** Absent for local events (work inside one party). */
  request: HttpRequestRecord | null
  response: HttpResponseRecord | null
  duration_ms: number | null
  note: string | null
  checks: Check[]
  data: Record<string, string>
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
