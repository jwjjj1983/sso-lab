import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, Code, Stage, Values } from '../components/PlaygroundParts'
import { SequenceDiagram } from '../components/SequenceDiagram'
import { Checks, TraceTimeline, type StepRef } from '../components/TraceTimeline'
import type { ProtocolSpec } from '../content/types'
import { api, ensureSession, type ExchangeResult } from '../lib/api'
import { stageStatus as stage, useAction } from '../lib/playground'
import { runInPopup } from '../lib/popup'
import { useTraceStream } from '../lib/useTraceStream'

type Mode = 'guided' | 'auto'

function Xml({ label, xml, open = false }: { label: string; xml: string; open?: boolean }) {
  return (
    <details open={open} className="text-xs">
      <summary className="cursor-pointer text-accent">{label}</summary>
      <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-surface-2 p-2 font-mono leading-relaxed">{xml}</pre>
    </details>
  )
}

export function SamlPlayground({ protocol, base }: { protocol: ProtocolSpec; base: string }) {
  const queryClient = useQueryClient()
  const [, setParams] = useSearchParams()
  const lab = useQuery({ queryKey: ['lab-session'], queryFn: ensureSession })
  const config = useQuery({ queryKey: ['lab-config'], queryFn: api.config })
  const labId = lab.data?.id
  const samlState = useQuery({ queryKey: ['saml-state', labId], queryFn: api.saml.state, enabled: !!labId })
  const { events, status } = useTraceStream(labId)

  const [mode, setMode] = useState<Mode>('guided')
  const [error, setError] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<{ idp: string; sp: string } | null>(null)
  const [validation, setValidation] = useState<ExchangeResult | null>(null)
  const [appBSignedIn, setAppBSignedIn] = useState(false)

  const samlEvents = useMemo(() => events.filter((e) => e.step?.startsWith('saml.')), [events])
  const completed = useMemo(
    () => new Set(samlEvents.flatMap((e) => [e.step, e.response_step]).filter((s): s is string => !!s)),
    [samlEvents],
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
  const common = {
    setError,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['saml-state'] }),
  }

  const fetchMetadata = useAction(common, api.saml.metadata, setMetadata)
  const signIn = useAction(
    common,
    () => runInPopup(`/rp/saml/login?mode=${mode}`, 'sso-lab:saml'),
    () => setValidation(null),
  )
  const validate = useAction(common, api.saml.validate, (r) => {
    setValidation(r)
    if (!r.ok) setError(r.error)
  })
  const openAppB = useAction(
    common,
    () =>
      runInPopup(`${appBUrl}/rp/saml/login?lab_session=${encodeURIComponent(labId ?? '')}`, 'sso-lab:saml', [
        appBOrigin ?? '',
      ]),
    () => setAppBSignedIn(true),
  )
  const signOutAppA = useAction(common, api.saml.logout, () => setValidation(null))
  const signOutEverywhere = useAction(
    common,
    () => runInPopup('/rp/oidc/logout?everywhere=true', 'sso-lab:oidc'),
    () => setValidation(null),
  )
  const newTrace = useMutation({
    mutationFn: api.createSession,
    onSuccess: (data) => {
      queryClient.setQueryData(['lab-session'], data)
      setMetadata(null)
      setValidation(null)
      setAppBSignedIn(false)
    },
  })

  const request = samlState.data?.request ?? null
  const response = samlState.data?.response ?? null
  const session = samlState.data?.session ?? null
  const busy = [fetchMetadata, signIn, validate, openAppB, signOutAppA, signOutEverywhere].some((m) => m.isPending)

  return (
    <div className="space-y-6">
      <section className="max-w-3xl space-y-2">
        <p>
          Sign in to App A with SAML. The same IdP as the OpenID Connect playground plays the Identity Provider, and
          every request lands in the trace below as it happens.
        </p>
        <p className="text-sm text-muted">
          One IdP, one session: if you already signed in through OpenID Connect, SAML sign-ins skip the password too.
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

          <Stage n={1} title="Exchange metadata" status={stage(completed.has('saml.metadata'), true)}>
            <p>
              Trust in SAML is set up once, by swapping metadata: App A learns the IdP's SSO URL and signing
              certificate, and the IdP learns App A's entity ID and ACS URL.
            </p>
            <Button onClick={() => fetchMetadata.mutate()} disabled={busy || !labId}>
              Fetch the IdP's metadata
            </Button>
            {metadata && (
              <div className="space-y-2">
                <Xml label="IdP metadata (what App A trusts)" xml={metadata.idp} />
                <Xml label="App A's metadata (what the IdP was given)" xml={metadata.sp} />
              </div>
            )}
          </Stage>

          <Stage n={2} title="Sign in" status={stage(!!response || !!session, true)}>
            <p>
              App A sends you to the IdP with an AuthnRequest. After you sign in, the IdP's page posts a signed
              response back to App A. Use <Code>alice</Code> / <Code>wonderland</Code> or <Code>bob</Code> /{' '}
              <Code>builder</Code>.
            </p>
            <fieldset className="space-y-1 text-sm">
              <legend className="sr-only">How App A should behave</legend>
              <label className="flex items-start gap-2">
                <input type="radio" name="saml-mode" checked={mode === 'guided'} onChange={() => setMode('guided')} />
                <span>
                  <strong>Step by step:</strong> App A stops once the response arrives, so you can validate it
                  yourself.
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="saml-mode" checked={mode === 'auto'} onChange={() => setMode('auto')} />
                <span>
                  <strong>All at once:</strong> App A validates straight away, like a real app.
                </span>
              </label>
            </fieldset>
            <Button onClick={() => signIn.mutate()} disabled={busy || !labId}>
              {session ? 'Sign in again' : 'Sign in with SAML'}
            </Button>
            {request && (
              <div className="space-y-2">
                <Values values={{ 'request ID': request.request_id }} />
                <Xml label="The AuthnRequest App A sent" xml={request.xml} />
              </div>
            )}
            {response && (
              <div className="space-y-2">
                <p>
                  The IdP's response reached App A's ACS URL as a cross-site form POST. The browser didn't send App
                  A's <Code>SameSite=Lax</Code> cookies with it, so App A found its request by{' '}
                  <Code>InResponseTo</Code> in its own server-side cache.
                </p>
                <Xml label="The SAML response (not trusted yet)" xml={response} />
              </div>
            )}
          </Stage>

          <Stage n={3} title="Validate the response" status={stage(!!session, !!response)}>
            <p>
              Anyone can post XML to an ACS URL. App A checks the signature against the certificate from the IdP's
              metadata, then every condition, and reads the user only from the part the signature covers.
            </p>
            <Button onClick={() => validate.mutate()} disabled={busy || !response}>
              Validate the SAML response
            </Button>
            {validation && validation.checks.length > 0 && <Checks checks={validation.checks} />}
            {session && (
              <div className="space-y-2">
                <p className="font-medium">Signed in to App A as {session.name || session.sub}.</p>
                <Values values={session.claims} />
                <Xml label="The assertion, as signed" xml={session.assertion} />
              </div>
            )}
          </Stage>

          <Stage n={4} title="Single sign-on" status={stage(appBSignedIn, !!session)}>
            <p>App B is a separate app on its own site, also using SAML. The IdP remembers you, so no password.</p>
            <Button onClick={() => openAppB.mutate()} disabled={busy || !session || !appBUrl}>
              Open App B and sign in
            </Button>
            {appBSignedIn && (
              <p>
                <span className="font-medium text-ok">No password asked.</span> In the trace, the IdP answered App B's
                request with the auto-posting form straight away.
              </p>
            )}
          </Stage>

          <Stage n={5} title="Sign out" status={stage(false, !!session)}>
            <p>
              "Everywhere" ends App A's and the IdP's sessions. Real SAML deployments use Single Logout (SLO) to reach
              every app, which the lab does not implement yet.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => signOutAppA.mutate()} disabled={busy || !session} secondary>
                Sign out of App A
              </Button>
              <Button onClick={() => signOutEverywhere.mutate()} disabled={busy} secondary>
                Sign out everywhere
              </Button>
            </div>
          </Stage>
        </section>
      </div>

      <section aria-labelledby="saml-trace-title" className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="saml-trace-title" className="text-lg font-semibold">
            Live trace
          </h2>
          <span className="text-sm text-muted" role="status">
            {status === 'live' ? `${samlEvents.length} events` : 'Connecting…'}
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
          events={samlEvents}
          stepRef={(id) => stepRefs.get(id)}
          onSelectStep={selectStep}
          emptyText="Nothing yet. Start with step 1 or 2 above."
        />
      </section>
    </div>
  )
}
