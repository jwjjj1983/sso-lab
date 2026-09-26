import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { JwtView } from '../components/JwtView'
import { SequenceDiagram } from '../components/SequenceDiagram'
import { Checks, TraceTimeline, type StepRef } from '../components/TraceTimeline'
import type { ProtocolSpec } from '../content/types'
import { api, ensureSession, type ExchangeResult } from '../lib/api'
import { runInPopup } from '../lib/popup'
import { useTraceStream } from '../lib/useTraceStream'

type Mode = 'guided' | 'auto'
type StageStatus = 'done' | 'current' | 'todo'

export function OidcPlayground({ protocol, base }: { protocol: ProtocolSpec; base: string }) {
  const queryClient = useQueryClient()
  const [, setParams] = useSearchParams()
  const lab = useQuery({ queryKey: ['lab-session'], queryFn: ensureSession })
  const config = useQuery({ queryKey: ['lab-config'], queryFn: api.config })
  const labId = lab.data?.id
  const oidcState = useQuery({ queryKey: ['oidc-state', labId], queryFn: api.oidc.state, enabled: !!labId })
  const { events, status } = useTraceStream(labId)

  const [mode, setMode] = useState<Mode>('guided')
  const [error, setError] = useState<string | null>(null)
  const [discovery, setDiscovery] = useState<unknown>(null)
  const [exchangeResult, setExchangeResult] = useState<ExchangeResult | null>(null)
  const [apiResult, setApiResult] = useState<{ title: string; body: unknown } | null>(null)
  const [appBSignedIn, setAppBSignedIn] = useState(false)

  const oidcEvents = useMemo(() => events.filter((e) => e.step?.startsWith('oidc.')), [events])
  const completed = useMemo(
    () => new Set(oidcEvents.flatMap((e) => [e.step, e.response_step]).filter((s): s is string => !!s)),
    [oidcEvents],
  )
  const stepRefs = useMemo(
    () => new Map(protocol.flow.steps.map((s, i) => [s.id, { id: s.id, number: i + 1, title: s.title } as StepRef])),
    [protocol],
  )
  const selectStep = (id: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('step', id)
      return next
    })

  const appBUrl = config.data?.actors['app-b']
  const appBOrigin = appBUrl ? new URL(appBUrl).origin : null
  const refreshState = () => queryClient.invalidateQueries({ queryKey: ['oidc-state'] })
  const common = { setError, onSettled: refreshState }

  const discover = useAction(common, api.oidc.discovery, setDiscovery)
  const signIn = useAction(
    common,
    () => runInPopup(`/rp/oidc/login?mode=${mode}`, 'sso-lab:oidc'),
    () => {
      setExchangeResult(null)
      setApiResult(null)
    },
  )
  const exchange = useAction(common, api.oidc.exchange, (r) => {
    setExchangeResult(r)
    if (!r.ok) setError(r.error)
  })
  const userinfo = useAction(common, api.oidc.userinfo, (r) =>
    setApiResult({ title: `GET /userinfo → ${r.status}`, body: r.body }),
  )
  const refreshTokens = useAction(common, api.oidc.refresh, (r) =>
    setApiResult({
      title: r.ok ? 'Refreshed: new access and refresh tokens' : 'Refresh failed',
      body: r.ok
        ? 'The IdP issued a new access token and a new refresh token. The old refresh token is now dead (rotation): replaying it would fail.'
        : r.error,
    }),
  )
  const openAppB = useAction(
    common,
    () =>
      runInPopup(`${appBUrl}/rp/oidc/login?lab_session=${encodeURIComponent(labId ?? '')}`, 'sso-lab:oidc', [
        appBOrigin ?? '',
      ]),
    () => setAppBSignedIn(true),
  )
  const signOutAppA = useAction(common, api.oidc.logout, () => {
    setExchangeResult(null)
    setApiResult(null)
  })
  const signOutEverywhere = useAction(
    common,
    () => runInPopup('/rp/oidc/logout?everywhere=true', 'sso-lab:oidc'),
    () => {
      setExchangeResult(null)
      setApiResult(null)
    },
  )
  const newTrace = useMutation({
    mutationFn: api.createSession,
    onSuccess: (data) => {
      queryClient.setQueryData(['lab-session'], data)
      setDiscovery(null)
      setExchangeResult(null)
      setApiResult(null)
      setAppBSignedIn(false)
    },
  })

  const login = oidcState.data?.login ?? null
  const session = oidcState.data?.session ?? null
  const discovered = completed.has('oidc.register')
  const hasCode = !!login?.code
  const busy = [discover, signIn, exchange, userinfo, refreshTokens, openAppB, signOutAppA, signOutEverywhere].some(
    (m) => m.isPending,
  )
  const stage = (done: boolean, available: boolean): StageStatus => (done ? 'done' : available ? 'current' : 'todo')

  return (
    <div className="space-y-6">
      <section className="max-w-3xl space-y-2">
        <p>
          Drive the authorization code flow yourself. App A is a real app, the IdP is a real OpenID Provider, and
          every request between them and your browser lands in the trace below as it happens.
        </p>
        <p className="text-sm text-muted">
          Tokens are shown here so you can inspect them. A real app never hands them to the browser: they stay on
          its server.
        </p>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        <section aria-label="Flow progress" className="min-w-0 space-y-2">
          <SequenceDiagram
            flow={protocol.flow}
            protocolPath={base}
            threats={protocol.threats}
            completed={completed}
            showDetails={false}
          />
          <p className="text-xs text-muted">
            Ticked steps have appeared in your trace. For the full explanation of a step, open it on the{' '}
            <Link to={`${base}/flow`} className="text-accent underline">
              Sequence
            </Link>{' '}
            tab.
          </p>
        </section>

        <section aria-label="Controls" className="min-w-0 space-y-3">
          {error && (
            <p role="alert" className="rounded-md border border-err/40 bg-surface p-3 text-sm text-err">
              {error}
            </p>
          )}

          <Stage n={1} title="Meet the IdP" status={stage(discovered, true)}>
            <p>
              Before any login, App A reads the IdP's discovery document and signing keys. Apps cache these, so it
              happens once.
            </p>
            <Button onClick={() => discover.mutate()} disabled={busy || !labId}>
              Fetch discovery document
            </Button>
            {discovery !== null && (
              <details className="text-xs">
                <summary className="cursor-pointer text-accent">Show the documents</summary>
                <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-surface-2 p-2 font-mono">
                  {JSON.stringify(discovery, null, 2)}
                </pre>
              </details>
            )}
          </Stage>

          <Stage n={2} title="Sign in" status={stage(hasCode || !!session, true)}>
            <p>
              A popup takes you from App A to the IdP's login page. Use <Code>alice</Code> / <Code>wonderland</Code>{' '}
              or <Code>bob</Code> / <Code>builder</Code>.
            </p>
            <fieldset className="space-y-1 text-sm">
              <legend className="sr-only">How App A should behave</legend>
              <label className="flex items-start gap-2">
                <input type="radio" name="mode" checked={mode === 'guided'} onChange={() => setMode('guided')} />
                <span>
                  <strong>Step by step:</strong> App A stops once the code arrives, so you can take the next steps
                  yourself.
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="mode" checked={mode === 'auto'} onChange={() => setMode('auto')} />
                <span>
                  <strong>All at once:</strong> App A goes straight through, like a real app.
                </span>
              </label>
            </fieldset>
            <Button onClick={() => signIn.mutate()} disabled={busy || !labId}>
              {session ? 'Sign in again' : 'Sign in with the lab IdP'}
            </Button>
            {login && (
              <Values
                values={{
                  state: login.state,
                  nonce: login.nonce,
                  code_verifier: login.code_verifier,
                  code_challenge: login.code_challenge,
                  ...(login.code ? { code: login.code } : {}),
                }}
              />
            )}
            {hasCode && (
              <p className="text-sm">
                App A holds a code and checked <Code>state</Code>. The code expires after 60 seconds, so redeem it
                soon. Or wait, and see what happens.
              </p>
            )}
          </Stage>

          <Stage n={3} title="Redeem the code" status={stage(!!session, hasCode)}>
            <p>
              App A sends the code and the PKCE verifier to the IdP on the back channel, then validates the ID token
              it gets back.
            </p>
            <Button onClick={() => exchange.mutate()} disabled={busy || !hasCode}>
              Exchange code for tokens
            </Button>
            {exchangeResult && exchangeResult.checks.length > 0 && <Checks checks={exchangeResult.checks} />}
            {session && (
              <details open className="text-sm">
                <summary className="cursor-pointer font-medium">
                  Signed in to App A as {session.name || session.sub}. See the ID token
                </summary>
                <div className="mt-2 space-y-3">
                  <JwtView token={session.id_token} />
                  <Values values={{ access_token: session.access_token, refresh_token: session.refresh_token }} />
                </div>
              </details>
            )}
          </Stage>

          <Stage n={4} title="Use the tokens" status={stage(false, !!session)}>
            <p>The access token lets App A call APIs for the user. The refresh token gets new tokens without a login.</p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => userinfo.mutate()} disabled={busy || !session}>
                Call /userinfo
              </Button>
              <Button onClick={() => refreshTokens.mutate()} disabled={busy || !session} secondary>
                Refresh tokens
              </Button>
            </div>
            {apiResult && (
              <div className="text-sm">
                <p className="font-medium">{apiResult.title}</p>
                <pre className="mt-1 overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs whitespace-pre-wrap">
                  {typeof apiResult.body === 'string' ? apiResult.body : JSON.stringify(apiResult.body, null, 2)}
                </pre>
              </div>
            )}
          </Stage>

          <Stage n={5} title="Single sign-on" status={stage(appBSignedIn, !!session)}>
            <p>
              App B is a separate app on its own site. Sign in there: the IdP recognises its own session cookie and
              skips the password.
            </p>
            <Button onClick={() => openAppB.mutate()} disabled={busy || !session || !appBUrl}>
              Open App B and sign in
            </Button>
            {appBSignedIn && (
              <p className="text-sm">
                <span className="font-medium text-ok">No password asked.</span> In the trace, the IdP answered{' '}
                <Code>/authorize</Code> with a redirect straight back to App B.{' '}
                <a href={appBUrl} target="_blank" rel="noopener noreferrer" className="text-accent underline">
                  Visit App B
                </a>
                .
              </p>
            )}
          </Stage>

          <Stage n={6} title="Sign out" status={stage(false, !!session)}>
            <p>
              Signing out of one app does not sign you out of the IdP. Try App A only, then sign in again: no password.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => signOutAppA.mutate()} disabled={busy || !session} secondary>
                Sign out of App A
              </Button>
              <Button onClick={() => signOutEverywhere.mutate()} disabled={busy} secondary>
                Sign out everywhere
              </Button>
            </div>
            {appBSignedIn && (
              <p className="text-xs text-muted">
                "Everywhere" ends App A's and the IdP's sessions. App B keeps its own until it expires, unless the
                apps implement OIDC front- or back-channel logout.
              </p>
            )}
          </Stage>
        </section>
      </div>

      <section aria-labelledby="trace-title" className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="trace-title" className="text-lg font-semibold">
            Live trace
          </h2>
          <span className="text-sm text-muted" role="status">
            {status === 'live' ? `${oidcEvents.length} events` : 'Connecting…'}
          </span>
          <button
            type="button"
            onClick={() => newTrace.mutate()}
            disabled={newTrace.isPending}
            className="ml-auto rounded-md border border-border px-3 py-1.5 text-sm"
          >
            Clear trace
          </button>
        </div>
        <TraceTimeline
          events={oidcEvents}
          stepRef={(id) => stepRefs.get(id)}
          onSelectStep={selectStep}
          emptyText="Nothing yet. Start with step 1 or 2 above."
        />
      </section>
    </div>
  )
}

/** A playground action: clears the error first, shows failures, and refreshes App A's state. */
function useAction<T>(
  common: { setError: (message: string | null) => void; onSettled: () => void },
  fn: () => Promise<T>,
  onOk?: (value: T) => void,
) {
  return useMutation({
    mutationFn: fn,
    onMutate: () => common.setError(null),
    onSuccess: (value) => onOk?.(value),
    onError: (err) => common.setError(err.message),
    onSettled: common.onSettled,
  })
}

function Stage({ n, title, status, children }: { n: number; title: string; status: StageStatus; children: ReactNode }) {
  return (
    <section
      aria-labelledby={`stage-${n}`}
      className={`space-y-3 rounded-lg border bg-surface p-4 ${status === 'current' ? 'border-accent' : 'border-border'} ${
        status === 'todo' ? 'opacity-70' : ''
      }`}
    >
      <h3 id={`stage-${n}`} className="flex items-center gap-2 font-semibold">
        <span
          className={`flex size-6 items-center justify-center rounded-full text-xs ${
            status === 'done' ? 'bg-ok text-surface' : status === 'current' ? 'bg-accent text-accent-fg' : 'bg-surface-2 text-muted'
          }`}
          aria-hidden
        >
          {status === 'done' ? '✓' : n}
        </span>
        {title}
        {status === 'done' && <span className="sr-only">(done)</span>}
      </h3>
      <div className="space-y-3 text-sm">{children}</div>
    </section>
  )
}

function Button({
  children,
  onClick,
  disabled,
  secondary,
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  secondary?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-2 text-sm font-medium disabled:opacity-40 ${
        secondary ? 'border border-border' : 'bg-accent text-accent-fg'
      }`}
    >
      {children}
    </button>
  )
}

function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
}

function Values({ values }: { values: Record<string, string> }) {
  return (
    <dl className="space-y-1 text-xs">
      {Object.entries(values).map(([name, value]) => (
        <div key={name} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2">
          <dt className="font-mono text-muted">{name}</dt>
          <dd className="font-mono break-all">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
