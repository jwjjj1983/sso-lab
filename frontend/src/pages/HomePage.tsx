import { Link } from 'react-router'
import { ResourceList } from '../components/ResourceList'
import { RichText } from '../components/RichText'
import { SsoDiagram } from '../components/SsoDiagram'
import { GENERAL_RESOURCES, PROTOCOLS } from '../content/protocols'

const EXAMPLES = [
  {
    title: '"Sign in with Google"',
    where: 'Consumer apps',
    body: 'A new app lets you skip creating a password. Google is the identity provider; the app never sees your Google password.',
    protocol: 'OpenID Connect',
  },
  {
    title: 'Your company dashboard',
    where: 'Workforce SSO',
    body: 'You sign in to Okta or Microsoft Entra ID in the morning, then open Slack, Salesforce and Workday without typing a password again.',
    protocol: 'SAML or OpenID Connect',
  },
  {
    title: '"Log in with GitHub"',
    where: 'Developer tools',
    body: 'A CI service asks to read your repositories. That is delegated access: the tool gets a token scoped to what you approved.',
    protocol: 'OAuth 2.0 (often with OIDC)',
  },
  {
    title: 'Selling to enterprises',
    where: 'B2B SaaS',
    body: 'A customer\'s IT team asks "do you support SSO?" They want their employees to sign in with the company IdP, and access to stop the day someone leaves.',
    protocol: 'SAML, increasingly OIDC',
  },
]

const VOCABULARY = [
  {
    term: 'Identity Provider (IdP)',
    body: 'The one place you actually sign in. It authenticates you and vouches for you to apps. Okta, Entra ID, Google and the lab IdP are all IdPs.',
  },
  {
    term: 'Relying Party / Service Provider',
    body: 'An app that trusts the IdP instead of checking passwords itself. OIDC says Relying Party (RP); SAML says Service Provider (SP).',
  },
  {
    term: 'Token / assertion',
    body: 'A signed statement from the IdP: "this is alice, for this app, valid for five minutes". OIDC uses JSON Web Tokens; SAML uses XML assertions.',
  },
  {
    term: 'Trust',
    body: 'Set up once, before any login: the app registers with the IdP and learns which keys the IdP signs with. Everything else rests on this.',
  },
  {
    term: 'Session',
    body: 'Each party remembers you with its own cookie. The IdP\'s session is what makes the next app instant; each app\'s session is what keeps you signed in there.',
  },
  {
    term: 'Federation',
    body: 'Trust across organisations: your employer\'s IdP vouching for you to another company\'s app.',
  },
]

const COMPARISON = [
  { row: 'Answers the question', values: ['May this app act for me?', 'Who is this user?', 'Who is this user?'] },
  { row: 'Main output', values: ['Access token', 'ID token (JWT) + access token', 'Signed XML assertion'] },
  { row: 'Format', values: ['JSON over HTTPS', 'JSON over HTTPS', 'XML'] },
  { row: 'Tokens travel via', values: ['Back channel', 'Back channel', 'The browser (form post)'] },
  { row: 'Typical use', values: ['API access, delegated permissions', 'Consumer and modern workforce sign-in', 'Enterprise workforce SSO'] },
]

export function HomePage() {
  return (
    <div className="space-y-16">
      <section className="space-y-4 pt-4">
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Single sign-on, one real request at a time
        </h1>
        <p className="max-w-2xl text-lg text-muted">
          You use SSO every day. SSO Lab shows you what actually happens: every redirect, form post and
          server-to-server call between your browser, an app and an identity provider, captured and explained as it
          happens.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link to="/protocols/oidc" className="rounded-md bg-accent px-4 py-2 font-medium text-accent-fg">
            Explore OpenID Connect
          </Link>
          <a href="#what-is-sso" className="rounded-md border border-border px-4 py-2 font-medium">
            What is SSO?
          </a>
        </div>
      </section>

      <section id="what-is-sso" aria-labelledby="what-is-sso-title" className="scroll-mt-4 space-y-4">
        <h2 id="what-is-sso-title" className="text-2xl font-semibold">
          What is single sign-on?
        </h2>
        <div className="max-w-3xl space-y-3 leading-relaxed">
          <p>
            Think of a festival wristband. You show your ticket and ID once at the gate, and every stage lets you in by
            glancing at the band. The stages never check your ID themselves; they trust the gate.
          </p>
          <p>
            Single sign-on works the same way. You prove who you are once, to an <strong>identity provider</strong>.
            Each app then trusts a short-lived, signed statement from that provider instead of keeping its own
            passwords. Fewer passwords to leak, one place to enforce MFA, and one switch to turn off when someone
            leaves.
          </p>
        </div>
        <SsoDiagram />
      </section>

      <section aria-labelledby="examples-title" className="space-y-4">
        <h2 id="examples-title" className="text-2xl font-semibold">
          You have used it today
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((e) => (
            <li key={e.title} className="space-y-2 rounded-lg border border-border bg-surface p-4">
              <p className="text-xs font-semibold tracking-wide text-muted uppercase">{e.where}</p>
              <h3 className="font-semibold">{e.title}</h3>
              <p className="text-sm">{e.body}</p>
              <p className="text-xs text-muted">
                Usually: <span className="font-medium text-fg">{e.protocol}</span>
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="vocab-title" className="space-y-4">
        <h2 id="vocab-title" className="text-2xl font-semibold">
          The vocabulary
        </h2>
        <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
          {VOCABULARY.map((v) => (
            <div key={v.term}>
              <dt className="font-semibold">{v.term}</dt>
              <dd className="mt-1 text-sm text-muted">{v.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="channels-title" className="space-y-4">
        <h2 id="channels-title" className="text-2xl font-semibold">
          The idea that explains everything: two channels
        </h2>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="mb-1">
              <span className="rounded bg-front-bg px-1.5 py-0.5 text-xs font-semibold text-front">Front channel</span>
            </p>
            <p className="text-sm">
              Messages the browser carries: redirects and form posts between the app and the IdP. Convenient, but the
              user, their extensions and their history can see and change everything in them.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="mb-1">
              <span className="rounded bg-back-bg px-1.5 py-0.5 text-xs font-semibold text-back">Back channel</span>
            </p>
            <p className="text-sm">
              Direct server-to-server calls, like the app redeeming a code for tokens. The browser never sees them, so
              this is where secrets and tokens should travel.
            </p>
          </div>
        </div>
        <p className="max-w-3xl text-sm text-muted">
          Most of the design of these protocols, and most of their attacks, come down to what is allowed to travel on
          which channel. The lab colours every request by its channel.
        </p>
      </section>

      <section aria-labelledby="protocols-title" className="space-y-4">
        <h2 id="protocols-title" className="text-2xl font-semibold">
          The protocols
        </h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] bg-surface text-left text-sm">
            <thead className="bg-surface-2">
              <tr>
                <th scope="col" className="p-3 font-semibold">
                  <span className="sr-only">Property</span>
                </th>
                <th scope="col" className="p-3 font-semibold">OAuth 2.0</th>
                <th scope="col" className="p-3 font-semibold">OpenID Connect</th>
                <th scope="col" className="p-3 font-semibold">SAML 2.0</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((r) => (
                <tr key={r.row} className="border-t border-border">
                  <th scope="row" className="p-3 font-medium text-muted">
                    {r.row}
                  </th>
                  {r.values.map((v, i) => (
                    <td key={i} className="p-3">
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="max-w-3xl text-sm text-muted">
          Related, but not sign-in protocols: <strong className="text-fg">SCIM</strong> creates and removes accounts in
          apps ahead of time; <strong className="text-fg">passkeys / WebAuthn</strong> are a way to prove who you are{' '}
          <em>to</em> the IdP; <strong className="text-fg">Kerberos</strong> and <strong className="text-fg">LDAP</strong>{' '}
          power sign-in inside corporate networks.
        </p>
      </section>

      <section aria-labelledby="explore-title" className="space-y-4">
        <h2 id="explore-title" className="text-2xl font-semibold">
          Pick a protocol
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2">
          {PROTOCOLS.map((p) => (
            <li key={p.slug}>
              <Link
                to={`/protocols/${p.slug}`}
                className="block h-full space-y-2 rounded-lg border border-border bg-surface p-5 hover:border-accent"
              >
                <p className="text-sm font-semibold text-accent">{p.shortName}</p>
                <h3 className="text-lg font-semibold">{p.name}</h3>
                <p className="text-sm text-muted">
                  <RichText text={p.tagline} />
                </p>
                <p className="text-sm font-medium text-accent">
                  Components, sequence diagram, security and further reading →
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="learn-title" className="space-y-4">
        <h2 id="learn-title" className="text-2xl font-semibold">
          Learn more
        </h2>
        <ResourceList resources={GENERAL_RESOURCES} grouped={false} />
      </section>
    </div>
  )
}
