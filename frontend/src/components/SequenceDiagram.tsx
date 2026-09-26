import { useRef, type KeyboardEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import type { FlowSpec, FlowStep, StepChannel, Threat } from '../content/types'
import { RichText } from './RichText'

// Geometry, in SVG user units. The SVG scales to its container; below ~560px wide the
// container scrolls horizontally instead of shrinking the text further.
const WIDTH = 660
const GUTTER = 110 // left/right margin to the outer lanes; step numbers live in the left one
const HEADER_HEIGHT = 48
const ROW_HEIGHT = 46
const TOP = HEADER_HEIGHT + 20

const CHANNELS: Record<
  StepChannel,
  // Full class names, so Tailwind can find them in the source.
  { label: string; hint: string; stroke: string; fill: string; dash?: string; badge: string }
> = {
  front: {
    label: 'Front channel',
    hint: 'Carried by the browser: visible in the address bar, history and dev tools.',
    stroke: 'stroke-front',
    fill: 'fill-front',
    badge: 'bg-front-bg text-front',
  },
  back: {
    label: 'Back channel',
    hint: 'Server to server: the browser never sees it.',
    stroke: 'stroke-back',
    fill: 'fill-back',
    dash: '7 4',
    badge: 'bg-back-bg text-back',
  },
  local: {
    label: 'Inside one party',
    hint: 'Work done by one party, no message sent.',
    stroke: 'stroke-muted',
    fill: 'fill-muted',
    badge: 'bg-surface-2 text-muted',
  },
  setup: {
    label: 'One-time setup',
    hint: 'Configuration done once, before any user signs in.',
    stroke: 'stroke-muted',
    fill: 'fill-muted',
    dash: '2 4',
    badge: 'bg-surface-2 text-muted',
  },
}

interface Props {
  flow: FlowSpec
  /** Base path of the protocol, for links to threats on the security tab. */
  protocolPath: string
  threats: Threat[]
  /** Steps already seen in the live trace (playground): drawn with a tick. */
  completed?: ReadonlySet<string>
  /** Show the step details panel next to the diagram (default true). */
  showDetails?: boolean
}

export function SequenceDiagram({ flow, protocolPath, threats, completed, showDetails = true }: Props) {
  const [params, setParams] = useSearchParams()
  const requested = flow.steps.findIndex((s) => s.id === params.get('step'))
  const activeIndex = requested >= 0 ? requested : 0
  const stepRefs = useRef<(SVGGElement | null)[]>([])

  const select = (index: number, focus = false) => {
    const clamped = Math.max(0, Math.min(flow.steps.length - 1, index))
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('step', flow.steps[clamped].id)
        return next
      },
      { replace: true, preventScrollReset: true },
    )
    if (focus) stepRefs.current[clamped]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent) => {
    const moves: Record<string, number> = {
      ArrowDown: 1,
      ArrowRight: 1,
      ArrowUp: -1,
      ArrowLeft: -1,
      Home: -Infinity,
      End: Infinity,
    }
    const move = moves[event.key]
    if (move === undefined) return
    event.preventDefault()
    const target = Number.isFinite(move) ? activeIndex + move : move < 0 ? 0 : flow.steps.length - 1
    select(target, true)
  }

  const laneX = new Map(
    flow.lanes.map((lane, i) => [
      lane.id,
      GUTTER + (i * (WIDTH - 2 * GUTTER)) / Math.max(1, flow.lanes.length - 1),
    ]),
  )
  const height = TOP + flow.steps.length * ROW_HEIGHT + 12
  const markerPrefix = `seq-${flow.id}`
  const active = flow.steps[activeIndex]

  return (
    <div className={showDetails ? 'grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]' : ''}>
      <div className="min-w-0 space-y-3">
        <Legend />
        <CompactStepList flow={flow} activeIndex={activeIndex} onSelect={select} completed={completed} />
        <div className="hidden overflow-x-auto rounded-lg border border-border bg-surface sm:block">
          <svg
            viewBox={`0 0 ${WIDTH} ${height}`}
            className="block w-full min-w-[540px]"
            role="group"
            aria-label={`Sequence diagram: ${flow.title}. Use the arrow keys to move between steps.`}
            onKeyDown={onKeyDown}
          >
            <defs>
              {(['front', 'back', 'setup'] as const).map((channel) => (
                <marker
                  key={channel}
                  id={`${markerPrefix}-${channel}`}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path
                    d="M0,0 L10,5 L0,10 z"
                    className={CHANNELS[channel].fill}
                  />
                </marker>
              ))}
            </defs>

            {flow.lanes.map((lane) => {
              const x = laneX.get(lane.id)!
              return (
                <g key={lane.id}>
                  <line
                    x1={x}
                    x2={x}
                    y1={HEADER_HEIGHT}
                    y2={height - 8}
                    className="stroke-border"
                    strokeDasharray="4 4"
                  />
                  <rect
                    x={x - 72}
                    y={8}
                    width={144}
                    height={HEADER_HEIGHT - 12}
                    rx={8}
                    className="fill-surface-2 stroke-border"
                  />
                  <text
                    x={x}
                    y={8 + (HEADER_HEIGHT - 12) / 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="fill-fg text-[13px] font-semibold"
                  >
                    {lane.label}
                  </text>
                </g>
              )
            })}

            {flow.steps.map((step, index) => (
              <StepRow
                key={step.id}
                ref={(el) => {
                  stepRefs.current[index] = el
                }}
                step={step}
                index={index}
                y={TOP + index * ROW_HEIGHT}
                laneX={laneX}
                active={index === activeIndex}
                done={completed?.has(step.id) ?? false}
                markerPrefix={markerPrefix}
                onSelect={() => select(index)}
              />
            ))}
          </svg>
        </div>
      </div>

      {showDetails && (
      <StepDetails
        key={active.id}
        flow={flow}
        step={active}
        index={activeIndex}
        protocolPath={protocolPath}
        threats={threats}
        onSelect={select}
      />
      )}
    </div>
  )
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label="Legend">
      {(Object.keys(CHANNELS) as StepChannel[]).map((channel) => (
        <li key={channel} className="flex items-center gap-1.5" title={CHANNELS[channel].hint}>
          <svg width="28" height="10" aria-hidden>
            {channel === 'local' ? (
              <rect x="4" y="1" width="20" height="8" rx="2" className="fill-surface-2 stroke-muted" />
            ) : (
              <line
                x1="0"
                x2="28"
                y1="5"
                y2="5"
                strokeWidth="2"
                strokeDasharray={CHANNELS[channel].dash}
                className={CHANNELS[channel].stroke}
              />
            )}
          </svg>
          {CHANNELS[channel].label}
        </li>
      ))}
    </ul>
  )
}

/** Phones: three lanes of arrows don't fit legibly, so show the steps as a list instead. */
function CompactStepList({
  flow,
  activeIndex,
  onSelect,
  completed,
}: {
  flow: FlowSpec
  activeIndex: number
  onSelect: (index: number) => void
  completed?: ReadonlySet<string>
}) {
  const lane = (id: string) => flow.lanes.find((l) => l.id === id)?.label ?? id
  return (
    <ol className="space-y-1 sm:hidden" aria-label={`Steps of ${flow.title}`}>
      {flow.steps.map((step, index) => {
        const channel = CHANNELS[step.channel]
        const active = index === activeIndex
        return (
          <li key={step.id}>
            <button
              type="button"
              onClick={() => onSelect(index)}
              aria-current={active ? 'step' : undefined}
              className={`flex w-full items-start gap-3 rounded-md border px-3 py-2 text-left ${
                active ? 'border-accent bg-accent/10' : 'border-border bg-surface'
              }`}
            >
              <span
                className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  active ? 'bg-accent text-accent-fg' : 'bg-surface-2 text-muted'
                }`}
              >
                {index + 1}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {step.label}
                  {completed?.has(step.id) && (
                    <span className="ml-1 text-ok" aria-label="(seen in the trace)">
                      ✓
                    </span>
                  )}
                </span>
                <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
                  <span>
                    {step.from === step.to ? `inside ${lane(step.from)}` : `${lane(step.from)} → ${lane(step.to)}`}
                  </span>
                  <span className={`rounded px-1 font-semibold ${channel.badge}`}>{channel.label}</span>
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

interface StepRowProps {
  ref: (el: SVGGElement | null) => void
  step: FlowStep
  index: number
  y: number
  laneX: Map<string, number>
  active: boolean
  done: boolean
  markerPrefix: string
  onSelect: () => void
}

function StepRow({ ref, step, index, y, laneX, active, done, markerPrefix, onSelect }: StepRowProps) {
  const mid = y + ROW_HEIGHT / 2
  const from = laneX.get(step.from)!
  const to = laneX.get(step.to)!
  const channel = CHANNELS[step.channel]
  const isLocal = step.channel === 'local'
  const boxWidth = Math.min(210, step.label.length * 6.6 + 24)

  return (
    <g
      ref={ref}
      role="button"
      tabIndex={active ? 0 : -1}
      aria-current={active ? 'step' : undefined}
      aria-label={`Step ${index + 1}: ${step.title}${done ? ' (seen in the trace)' : ''}`}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className="seq-step cursor-pointer outline-none"
    >
      <rect
        x={4}
        y={y + 2}
        width={WIDTH - 8}
        height={ROW_HEIGHT - 4}
        rx={8}
        className={`seq-band ${active ? 'fill-accent/12' : 'fill-transparent hover:fill-surface-2'}`}
      />
      <circle
        cx={28}
        cy={mid}
        r={11}
        className={active ? 'fill-accent' : done ? 'fill-ok' : 'fill-surface-2'}
      />
      <text
        x={28}
        y={mid}
        textAnchor="middle"
        dominantBaseline="central"
        className={`text-[11px] font-semibold ${active ? 'fill-accent-fg' : done ? 'fill-surface' : 'fill-muted'}`}
      >
        {done && !active ? '✓' : index + 1}
      </text>

      {isLocal ? (
        <>
          <rect
            x={from - boxWidth / 2}
            y={mid - 13}
            width={boxWidth}
            height={26}
            rx={6}
            className={`fill-surface ${active ? 'stroke-accent' : 'stroke-muted'}`}
            strokeWidth={active ? 2 : 1}
          />
          <text x={from} y={mid} textAnchor="middle" dominantBaseline="central" className="fill-fg text-[12px]">
            {step.label}
          </text>
        </>
      ) : (
        <>
          <line
            x1={from + Math.sign(to - from) * 4}
            x2={to - Math.sign(to - from) * 6}
            y1={mid + 7}
            y2={mid + 7}
            className={channel.stroke}
            strokeWidth={active ? 2.5 : 1.75}
            strokeDasharray={channel.dash}
            markerEnd={`url(#${markerPrefix}-${step.channel})`}
          />
          <text
            x={(from + to) / 2}
            y={mid - 5}
            textAnchor="middle"
            className={`text-[12px] ${active ? 'fill-fg font-semibold' : 'fill-fg'}`}
          >
            {step.label}
          </text>
        </>
      )}
    </g>
  )
}

interface StepDetailsProps {
  flow: FlowSpec
  step: FlowStep
  index: number
  protocolPath: string
  threats: Threat[]
  onSelect: (index: number) => void
}

function StepDetails({ flow, step, index, protocolPath, threats, onSelect }: StepDetailsProps) {
  const lane = (id: string) => flow.lanes.find((l) => l.id === id)?.label ?? id
  const channel = CHANNELS[step.channel]
  const defends = (step.threats ?? [])
    .map((id) => threats.find((t) => t.id === id))
    .filter((t): t is Threat => t !== undefined)

  return (
    <section
      aria-live="polite"
      aria-labelledby={`step-title-${step.id}`}
      className="min-w-0 space-y-4 self-start rounded-lg border border-border bg-surface p-4 xl:sticky xl:top-4"
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold text-muted">
          Step {index + 1} of {flow.steps.length}
        </span>
        <span className={`rounded px-1.5 py-0.5 font-semibold ${channel.badge}`} title={channel.hint}>
          {channel.label}
        </span>
        <span className="text-muted">
          {step.from === step.to ? `inside ${lane(step.from)}` : `${lane(step.from)} → ${lane(step.to)}`}
        </span>
      </div>

      <h3 id={`step-title-${step.id}`} className="text-lg font-semibold">
        {step.title}
      </h3>
      <p>
        <RichText text={step.summary} />
      </p>
      {step.details?.map((d, i) => (
        <p key={i} className="text-sm text-muted">
          <RichText text={d} />
        </p>
      ))}

      {step.checks && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">What gets checked</h4>
          <ul className="space-y-1 text-sm">
            {step.checks.map((check) => (
              <li key={check} className="flex gap-2">
                <span aria-hidden className="text-ok">
                  ✓
                </span>
                <span>
                  <RichText text={check} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {step.http && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Example</h4>
          <pre className="max-h-80 overflow-auto rounded-md bg-surface-2 p-3 font-mono text-xs leading-relaxed">
            {step.http}
          </pre>
        </div>
      )}

      {defends.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Defends against</h4>
          <ul className="flex flex-wrap gap-2">
            {defends.map((t) => (
              <li key={t.id}>
                <Link
                  to={`${protocolPath}/security#${t.id}`}
                  className="inline-block rounded-full border border-border px-2 py-0.5 text-xs hover:border-accent hover:text-accent"
                >
                  <RichText text={t.name} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-between gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={() => onSelect(index - 1)}
          disabled={index === 0}
          className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-40"
        >
          ← Previous
        </button>
        <button
          type="button"
          onClick={() => onSelect(index + 1)}
          disabled={index === flow.steps.length - 1}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:opacity-40"
        >
          Next →
        </button>
      </div>
    </section>
  )
}
