import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { TraceEvent } from '../lib/trace'
import { TraceTimeline } from './TraceTimeline'

const tokenCall: TraceEvent = {
  id: 'e1',
  lab_session_id: 's',
  ts: '2026-01-01T00:00:00Z',
  channel: 'back',
  source: 'app-a',
  target: 'idp',
  step: 'diag.back-channel',
  request: {
    method: 'GET',
    url: 'http://idp.localhost:8000/diag/ping',
    headers: [{ name: 'accept', value: '*/*' }],
    body: null,
  },
  response: { status: 200, headers: [], body: '{"actor":"idp"}' },
  duration_ms: 3.2,
  note: null,
}

describe('TraceTimeline', () => {
  it('explains that the trace is empty', () => {
    render(<TraceTimeline events={[]} />)
    expect(screen.getByText(/no requests yet/i)).toBeInTheDocument()
  })

  it('summarises each hop and expands to the raw messages', async () => {
    render(<TraceTimeline events={[tokenCall]} />)
    const row = screen.getByRole('button', { name: /back channel/i })
    expect(row).toHaveTextContent('App A → IdP')
    expect(row).toHaveTextContent('/diag/ping')
    expect(row).toHaveAttribute('aria-expanded', 'false')

    await userEvent.click(row)

    expect(row).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('GET http://idp.localhost:8000/diag/ping')).toBeInTheDocument()
    expect(screen.getByText(/"actor":"idp"/)).toBeInTheDocument()
  })
})
