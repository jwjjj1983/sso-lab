import { mergeEvents, type TraceEvent } from './trace'

function event(id: string, ts: string): TraceEvent {
  return {
    id,
    lab_session_id: 's',
    ts,
    channel: 'back',
    source: 'app-a',
    target: 'idp',
    step: null,
    request: { method: 'GET', url: 'http://idp/x', headers: [], body: null },
    response: null,
    duration_ms: null,
    note: null,
    response_step: null,
    checks: [],
    data: {},
  }
}

describe('mergeEvents', () => {
  it('ignores events already in the trace (the stream replays history on reconnect)', () => {
    const a = event('a', '2026-01-01T00:00:01Z')
    const current = [a]
    expect(mergeEvents(current, [a])).toBe(current)
  })

  it('keeps events in time order', () => {
    const late = event('late', '2026-01-01T00:00:02Z')
    const early = event('early', '2026-01-01T00:00:01Z')
    expect(mergeEvents([late], [early]).map((e) => e.id)).toEqual(['early', 'late'])
  })
})
