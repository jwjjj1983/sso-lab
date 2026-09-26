import type { Resource, ResourceKind } from '../content/types'
import { RichText } from './RichText'

const GROUPS: { kind: ResourceKind; title: string }[] = [
  { kind: 'video', title: 'Watch' },
  { kind: 'guide', title: 'Read' },
  { kind: 'security', title: 'Security' },
  { kind: 'spec', title: 'Specifications' },
]

const ICONS: Record<ResourceKind, string> = {
  video: '▶',
  guide: '✎',
  security: '⚠',
  spec: '§',
}

export function ResourceList({ resources, grouped = true }: { resources: Resource[]; grouped?: boolean }) {
  if (!grouped) return <Items resources={resources} />
  return (
    <div className="grid gap-8 md:grid-cols-2">
      {GROUPS.map(({ kind, title }) => {
        const items = resources.filter((r) => r.kind === kind)
        if (items.length === 0) return null
        return (
          <section key={kind} aria-labelledby={`resources-${kind}`}>
            <h3 id={`resources-${kind}`} className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
              {title}
            </h3>
            <Items resources={items} />
          </section>
        )
      })}
    </div>
  )
}

function Items({ resources }: { resources: Resource[] }) {
  return (
    <ul className="space-y-3">
      {resources.map((r) => (
        <li key={r.url} className="flex gap-3">
          <span aria-hidden className="mt-0.5 w-4 shrink-0 text-center text-muted">
            {ICONS[r.kind]}
          </span>
          <div className="min-w-0">
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-accent underline-offset-2 hover:underline"
            >
              {r.title}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            <p className="text-sm text-muted">
              {r.source} · <RichText text={r.note} />
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}
