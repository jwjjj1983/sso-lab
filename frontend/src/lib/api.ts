import type { Actor, Check } from './trace'

export interface LabSession {
  id: string
  expires_at: string
}

export interface PingResult {
  target: Actor
  status: number | null
  error: string | null
}

export interface LabConfig {
  actors: Record<'idp' | 'app-a' | 'app-b', string>
}

/** What App A holds for this browser (see backend lab/oidc_api.py). */
export interface OidcState {
  login: {
    state: string
    nonce: string
    code_verifier: string
    code_challenge: string
    mode: 'guided' | 'auto'
    code: string | null
  } | null
  session: {
    sub: string
    name: string
    email: string
    claims: Record<string, unknown>
    id_token: string
    access_token: string
    refresh_token: string
  } | null
}

/** What App A holds for this browser in the SAML flow (see backend lab/saml_api.py). */
export interface SamlState {
  request: { request_id: string; xml: string; encoded: string } | null
  /** The IdP's response, posted to App A's ACS and waiting to be validated. */
  response: string | null
  session: {
    sub: string
    name: string
    email: string
    claims: Record<string, string>
    assertion: string
  } | null
}

export interface ExchangeResult {
  ok: boolean
  error: string | null
  checks: Check[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string): Promise<T> {
  const resp = await fetch(path, { method, credentials: 'same-origin' })
  if (!resp.ok) {
    let detail = `${method} ${path} failed with ${resp.status}`
    try {
      const body = await resp.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // not JSON: keep the generic message
    }
    throw new ApiError(resp.status, detail)
  }
  return (await resp.json()) as T
}

export const api = {
  config: () => request<LabConfig>('GET', '/api/lab/config'),
  currentSession: () => request<LabSession>('GET', '/api/lab/session'),
  createSession: () => request<LabSession>('POST', '/api/lab/sessions'),
  backChannelDiagnostic: () => request<PingResult[]>('POST', '/api/lab/diagnostics/back-channel'),
  oidc: {
    discovery: () =>
      request<{ discovery: Record<string, unknown>; jwks: { keys: Record<string, unknown>[] } }>(
        'POST',
        '/api/lab/oidc/discovery',
      ),
    state: () => request<OidcState>('GET', '/api/lab/oidc/state'),
    exchange: () => request<ExchangeResult>('POST', '/api/lab/oidc/exchange'),
    userinfo: () => request<{ status: number; body: unknown }>('POST', '/api/lab/oidc/userinfo'),
    refresh: () => request<{ ok: boolean; error: string | null }>('POST', '/api/lab/oidc/refresh'),
    logout: () => request<{ ok: boolean }>('POST', '/api/lab/oidc/logout'),
  },
  saml: {
    metadata: () => request<{ idp: string; sp: string }>('POST', '/api/lab/saml/metadata'),
    state: () => request<SamlState>('GET', '/api/lab/saml/state'),
    validate: () => request<ExchangeResult>('POST', '/api/lab/saml/validate'),
    // App A keeps one session cookie, whichever protocol signed you in.
    logout: () => request<{ ok: boolean }>('POST', '/api/lab/oidc/logout'),
  },
}

/** The current lab session, creating one if the visitor has none yet. */
export async function ensureSession(): Promise<LabSession> {
  try {
    return await api.currentSession()
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return api.createSession()
    throw err
  }
}
