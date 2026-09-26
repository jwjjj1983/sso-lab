import { useEffect } from 'react'
import { Link, NavLink, Navigate, useLocation, useParams } from 'react-router'
import { ResourceList } from '../components/ResourceList'
import { RichText } from '../components/RichText'
import { SequenceDiagram } from '../components/SequenceDiagram'
import { getProtocol } from '../content/protocols'
import type { Component, ProtocolSpec } from '../content/types'
import { OidcPlayground } from './OidcPlayground'
import { SamlPlayground } from './SamlPlayground'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'components', label: 'Components' },
  { id: 'flow', label: 'Sequence' },
  { id: 'playground', label: 'Playground' },
  { id: 'security', label: 'Security' },
  { id: 'learn', label: 'Learn more' },
] as const

type TabId = (typeof TABS)[number]['id']

export function ProtocolPage() {
  const { slug, tab = 'overview' } = useParams()
  const protocol = getProtocol(slug)
  if (!protocol) return <p className="text-muted">No such protocol.</p>
  if (!TABS.some((t) => t.id === tab)) return <Navigate to={`/protocols/${protocol.slug}`} replace />

  const base = `/protocols/${protocol.slug}`
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="text-sm font-semibold text-accent">{protocol.shortName}</p>
        <h1 className="text-3xl font-semibold tracking-tight">{protocol.name}</h1>
        <p className="max-w-3xl text-lg text-muted">{protocol.tagline}</p>
      </header>

      <nav aria-label={`${protocol.name} sections`} className="-mx-4 overflow-x-auto px-4">
        <ul className="flex min-w-max gap-1 border-b border-border">
          {TABS.map((t) => (
            <li key={t.id}>
              <NavLink
                to={t.id === 'overview' ? base : `${base}/${t.id}`}
                end
                className={({ isActive }) =>
                  `-mb-px block border-b-2 px-3 py-2 text-sm ${
                    isActive ? 'border-accent font-medium text-fg' : 'border-transparent text-muted hover:text-fg'
                  }`
                }
              >
                {t.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <TabContent protocol={protocol} tab={tab as TabId} base={base} />
    </div>
  )
}

function TabContent({ protocol, tab, base }: { protocol: ProtocolSpec; tab: TabId; base: string }) {
  switch (tab) {
    case 'overview':
      return <Overview protocol={protocol} base={base} />
    case 'components':
      return <Components protocol={protocol} />
    case 'flow':
      return (
        <section className="space-y-4">
          <div className="space-y-1">
            <h2 className="text-xl font-semibold">{protocol.flow.title}</h2>
            <p className="max-w-3xl text-muted">{protocol.flow.description}</p>
          </div>
          <SequenceDiagram flow={protocol.flow} protocolPath={base} threats={protocol.threats} />
        </section>
      )
    case 'playground':
      if (protocol.slug === 'oidc') return <OidcPlayground protocol={protocol} base={base} />
      if (protocol.slug === 'saml') return <SamlPlayground protocol={protocol} base={base} />
      return <Playground protocol={protocol} base={base} />
    case 'security':
      return <Security protocol={protocol} base={base} />
    case 'learn':
      return <ResourceList resources={protocol.resources} />
  }
}

function Overview({ protocol, base }: { protocol: ProtocolSpec; base: string }) {
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <div className="space-y-6">
        <section className="space-y-3">
          {protocol.overview.whatItIs.map((p, i) => (
            <p key={i} className="max-w-3xl leading-relaxed">
              <RichText text={p} />
            </p>
          ))}
        </section>
        <div className="grid gap-4 sm:grid-cols-2">
          <ListCard title="Reach for it when" items={protocol.overview.useWhen} tone="ok" />
          <ListCard title="Think twice when" items={protocol.overview.avoidWhen} tone="warn" />
        </div>
        <Link
          to={`${base}/flow`}
          className="inline-block rounded-md bg-accent px-4 py-2 font-medium text-accent-fg"
        >
          Walk through the flow step by step →
        </Link>
      </div>
      <aside aria-label="At a glance" className="self-start rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">At a glance</h2>
        <dl className="space-y-3 text-sm">
          {protocol.facts.map((f) => (
            <div key={f.label}>
              <dt className="text-muted">{f.label}</dt>
              <dd className="font-medium">{f.value}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  )
}

function ListCard({ title, items, tone }: { title: string; items: string[]; tone: 'ok' | 'warn' }) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className={`mb-2 font-semibold ${tone === 'ok' ? 'text-ok' : 'text-warn'}`}>{title}</h2>
      <ul className="list-disc space-y-1.5 pl-5 text-sm">
        {items.map((item) => (
          <li key={item}>
            <RichText text={item} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function Components({ protocol }: { protocol: ProtocolSpec }) {
  return (
    <div className="space-y-8">
      <ComponentGrid title="Who is involved" items={protocol.components} />
      <ComponentGrid title="What they exchange" items={protocol.artifacts} />
    </div>
  )
}

function ComponentGrid({ title, items }: { title: string; items: Component[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => (
          <li key={c.term} className="space-y-2 rounded-lg border border-border bg-surface p-4">
            <h3 className="font-semibold">{c.term}</h3>
            {c.aka && (
              <p className="text-xs text-muted">
                Also called{' '}
                {c.aka.map((a, i) => (
                  <span key={a}>
                    {i > 0 && ', '}
                    <RichText text={a} />
                  </span>
                ))}
              </p>
            )}
            <p className="text-sm">
              <RichText text={c.description} />
            </p>
            <p className="text-xs text-muted">
              In the lab: <RichText text={c.inLab} />
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Playground({ protocol, base }: { protocol: ProtocolSpec; base: string }) {
  return (
    <section className="max-w-2xl space-y-4 rounded-lg border border-dashed border-border p-6">
      <h2 className="text-xl font-semibold">Playground: coming soon</h2>
      <p>{protocol.playgroundStatus}</p>
      <p className="text-muted">
        You will drive each step of the <Link to={`${base}/flow`} className="text-accent underline">flow</Link>{' '}
        yourself, sign in as a demo user, and see the real requests between your browser, App A and the IdP as
        they happen, with tokens and assertions decoded and every check explained.
      </p>
      <p className="text-muted">
        The live trace that will power it already works:{' '}
        <Link to="/lab/diagnostics" className="text-accent underline">
          try the lab diagnostics
        </Link>
        .
      </p>
    </section>
  )
}

function Security({ protocol, base }: { protocol: ProtocolSpec; base: string }) {
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [hash])

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-muted">
        Almost every real-world SSO breach comes from a check that was skipped, not from broken cryptography.
        Each of these attacks is stopped by a specific check in the flow.
      </p>
      <ul className="space-y-3">
        {protocol.threats.map((t) => {
          const steps = protocol.flow.steps
            .map((s, i) => ({ step: s, number: i + 1 }))
            .filter(({ step }) => step.threats?.includes(t.id))
          return (
            <li
              key={t.id}
              id={t.id}
              className={`scroll-mt-4 rounded-lg border bg-surface p-4 ${
                hash === `#${t.id}` ? 'border-accent' : 'border-border'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">
                  <RichText text={t.name} />
                </h2>
                {t.attackLab && (
                  <span className="rounded-full bg-front-bg px-2 py-0.5 text-xs font-semibold text-front">
                    Hands-on in the Attack Lab (coming)
                  </span>
                )}
              </div>
              <dl className="mt-2 grid gap-3 text-sm md:grid-cols-2">
                <div>
                  <dt className="font-medium text-err">The attack</dt>
                  <dd>
                    <RichText text={t.attack} />
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ok">The defense</dt>
                  <dd>
                    <RichText text={t.defense} />
                  </dd>
                </div>
              </dl>
              {steps.length > 0 && (
                <p className="mt-3 text-xs text-muted">
                  Checked at{' '}
                  {steps.map(({ step, number }, i) => (
                    <span key={step.id}>
                      {i > 0 && ', '}
                      <Link to={`${base}/flow?step=${step.id}`} className="text-accent underline-offset-2 hover:underline">
                        step {number}: {step.title}
                      </Link>
                    </span>
                  ))}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
