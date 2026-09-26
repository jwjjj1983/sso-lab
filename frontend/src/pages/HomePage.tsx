import { Link } from 'react-router'

const PROTOCOLS = [
  {
    name: 'OpenID Connect',
    tagline: 'Sign-in built on top of OAuth 2.0: authorization code flow with PKCE.',
    status: 'Coming in milestone 2',
  },
  {
    name: 'SAML 2.0',
    tagline: 'XML-based enterprise SSO: SP-initiated login with signed assertions.',
    status: 'Planned',
  },
]

// Milestone 1 replaces this with the full "What is SSO?" introduction.
export function HomePage() {
  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Single sign-on, one real request at a time
        </h1>
        <p className="max-w-2xl text-lg text-muted">
          Log in once and every app trusts you. SSO Lab lets you drive the protocols behind that
          yourself: every redirect, form post and server-to-server call is captured and explained
          as it happens.
        </p>
      </section>

      <section aria-labelledby="protocols" className="space-y-3">
        <h2 id="protocols" className="text-lg font-semibold">
          Protocols
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2">
          {PROTOCOLS.map((p) => (
            <li key={p.name} className="rounded-lg border border-border bg-surface p-4">
              <h3 className="font-semibold">{p.name}</h3>
              <p className="mt-1 text-sm text-muted">{p.tagline}</p>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-accent">
                {p.status}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-border bg-surface p-4">
        <h2 className="font-semibold">Check the lab plumbing</h2>
        <p className="mt-1 text-sm text-muted">
          Send real traffic between the lab's three sites and watch the trace stream in.
        </p>
        <Link
          to="/lab/diagnostics"
          className="mt-3 inline-block rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg"
        >
          Open diagnostics
        </Link>
      </section>
    </div>
  )
}
