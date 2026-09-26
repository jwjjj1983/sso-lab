import type { ReactNode } from 'react'

// "Without SSO" vs "With SSO", side by side (stacked on narrow screens).

const APPS = ['Mail', 'Docs', 'Payroll']

function Panel({ title, caption, children }: { title: string; caption: string; children: ReactNode }) {
  return (
    <figure className="rounded-lg border border-border bg-surface p-4">
      <figcaption className="mb-2">
        <span className="font-semibold">{title}</span>
        <span className="block text-sm text-muted">{caption}</span>
      </figcaption>
      {children}
    </figure>
  )
}

function Person({ x, y }: { x: number; y: number }) {
  return (
    <g aria-hidden>
      <circle cx={x} cy={y - 14} r={9} className="fill-muted" />
      <path d={`M${x - 15},${y + 14} a15,15 0 0 1 30,0 z`} className="fill-muted" />
    </g>
  )
}

function Box({ x, y, label, tone }: { x: number; y: number; label: string; tone: 'app' | 'idp' }) {
  return (
    <g>
      <rect
        x={x - 44}
        y={y - 16}
        width={88}
        height={32}
        rx={7}
        className={tone === 'idp' ? 'fill-accent stroke-accent' : 'fill-surface-2 stroke-border'}
      />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        className={`text-[13px] font-semibold ${tone === 'idp' ? 'fill-accent-fg' : 'fill-fg'}`}
      >
        {label}
      </text>
    </g>
  )
}

export function SsoDiagram() {
  const appY = [40, 100, 160]
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Without SSO" caption="Every app has its own login, password database and password reset.">
        <svg viewBox="0 0 320 200" className="mx-auto w-full max-w-sm" role="img" aria-label="One person with a separate password for each of three apps">
          <Person x={40} y={100} />
          {APPS.map((app, i) => (
            <g key={app}>
              <line x1={62} y1={100} x2={214} y2={appY[i]} className="stroke-err" strokeWidth={1.5} />
              <text
                x={62 + 0.55 * (214 - 62)}
                y={100 + 0.55 * (appY[i] - 100) - 7}
                textAnchor="middle"
                strokeWidth={5}
                paintOrder="stroke"
                className="fill-err stroke-surface text-[11px]"
              >
                password {i + 1}
              </text>
              <Box x={262} y={appY[i]} label={app} tone="app" />
            </g>
          ))}
        </svg>
      </Panel>
      <Panel title="With SSO" caption="You sign in once at the identity provider; every app trusts it.">
        <svg viewBox="0 0 320 200" className="mx-auto w-full max-w-sm" role="img" aria-label="One person signs in once at an identity provider, which vouches for them to three apps">
          <Person x={30} y={100} />
          <line x1={50} y1={100} x2={100} y2={100} className="stroke-ok" strokeWidth={2} />
          <text x={75} y={90} textAnchor="middle" className="fill-ok text-[11px]">
            once
          </text>
          <Box x={146} y={100} label="IdP" tone="idp" />
          {APPS.map((app, i) => (
            <g key={app}>
              <line
                x1={190}
                y1={100}
                x2={218}
                y2={appY[i]}
                className="stroke-accent"
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
              <Box x={262} y={appY[i]} label={app} tone="app" />
            </g>
          ))}
        </svg>
      </Panel>
    </div>
  )
}
