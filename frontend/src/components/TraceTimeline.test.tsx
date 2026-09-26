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
  response_step: null,
  checks: [],
  data: {},
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

  it('shows local work with its checks, and links hops to diagram steps', async () => {
    const validate: TraceEvent = {
      ...tokenCall,
      id: 'e2',
      channel: 'local',
      target: 'app-a',
      step: 'oidc.validate',
      request: null,
      response: null,
      duration_ms: null,
      note: 'App A rejected the ID token.',
      checks: [
        { label: 'iss is the expected IdP', ok: true, detail: null },
        { label: 'aud contains app-a', ok: false, detail: "aud = 'app-b'" },
      ],
      data: { id_token_payload: '{"aud": "app-b"}' },
    }
    const onSelectStep = vi.fn()
    render(
      <TraceTimeline
        events={[validate]}
        stepRef={(id) => (id === 'oidc.validate' ? { id, number: 11, title: 'App A validates the ID token' } : undefined)}
        onSelectStep={onSelectStep}
      />,
    )

    const row = screen.getByRole('button', { name: /inside app a/i })
    expect(row).toHaveTextContent('App A rejected the ID token.')
    expect(row).toHaveTextContent('1/2 checks passed')

    await userEvent.click(row)
    expect(screen.getByText('Failed:')).toBeInTheDocument()
    expect(screen.getByText("aud = 'app-b'")).toBeInTheDocument()
    expect(screen.getByText('{"aud": "app-b"}')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Step 11: App A validates the ID token' }))
    expect(onSelectStep).toHaveBeenCalledWith('oidc.validate')
  })
})
