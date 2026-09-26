import type { Actor } from './trace'

export interface LabSession {
  id: string
  expires_at: string
}

export interface PingResult {
  target: Actor
  status: number | null
  error: string | null
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
    throw new ApiError(resp.status, `${method} ${path} failed with ${resp.status}`)
  }
  return (await resp.json()) as T
}

export const api = {
  config: () => request<{ actors: Record<Exclude<Actor, 'browser' | 'external'>, string> }>('GET', '/api/lab/config'),
  currentSession: () => request<LabSession>('GET', '/api/lab/session'),
  createSession: () => request<LabSession>('POST', '/api/lab/sessions'),
  backChannelDiagnostic: () => request<PingResult[]>('POST', '/api/lab/diagnostics/back-channel'),
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
