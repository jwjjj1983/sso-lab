import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ProtocolPage } from './ProtocolPage'

class FakeEventSource {
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  addEventListener() {}
  close() {}
}

let samlState: unknown
const calls: string[] = []

function respond(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
}

beforeEach(() => {
  calls.length = 0
  samlState = {
    request: { request_id: '_req1', xml: '<samlp:AuthnRequest ID="_req1"/>', encoded: 'fZ...' },
    response: '<samlp:Response InResponseTo="_req1"/>',
    session: null,
  }
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${path}`)
      if (path === '/api/lab/session') return respond({ id: 'lab1', expires_at: '' })
      if (path === '/api/lab/config') return respond({ actors: { idp: 'http://idp', 'app-a': 'http://a', 'app-b': 'http://b' } })
      if (path === '/api/lab/saml/state') return respond(samlState)
      if (path === '/api/lab/saml/validate') {
        samlState = {
          ...(samlState as object),
          response: null,
          session: { sub: 'alice@example.com', name: 'Alice Liddell', email: 'alice@example.com', claims: { NameID: 'alice@example.com' }, assertion: '<saml:Assertion/>' },
        }
        return respond({ ok: true, error: null, checks: [{ label: 'the signature is valid', ok: true, detail: null }] })
      }
      return Promise.resolve(new Response('{}', { status: 404 }))
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function renderPlayground() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/protocols/saml/playground']}>
        <Routes>
          <Route path="/protocols/:slug/:tab?" element={<ProtocolPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SAML playground', () => {
  it('shows the pending response and validates it into a session', async () => {
    renderPlayground()

    expect(await screen.findByText(/found its request by/)).toBeInTheDocument()
    const validate = screen.getByRole('button', { name: 'Validate the SAML response' })
    expect(validate).toBeEnabled()

    await userEvent.click(validate)

    expect(calls).toContain('POST /api/lab/saml/validate')
    const stage = screen.getByRole('region', { name: /validate the response/i })
    expect(await within(stage).findByText('Signed in to App A as Alice Liddell.')).toBeInTheDocument()
    expect(within(stage).getByText('the signature is valid')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Validate the SAML response' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Open App B and sign in' })).toBeEnabled()
  })
})
