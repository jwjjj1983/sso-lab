// The content model. One ProtocolSpec per protocol drives its whole page: overview,
// components, the sequence diagram, the security tab and the reading list. The flow's step ids
// are also the `step` values the backend recorder attaches to trace events (from M2), so the
// playground can highlight the diagram step a live request belongs to.
//
// Prose strings may use `backticks` for inline code (see RichText).

export type LaneKind = 'browser' | 'app' | 'idp'

export interface Lane {
  id: string
  label: string
  /** Which lab actor plays this part. */
  kind: LaneKind
  description: string
}

/**
 * - front: an HTTP message carried by the browser (redirects, form posts)
 * - back: server to server, invisible to the browser
 * - local: work done inside one party (drawn as a note on its lane)
 * - setup: one-time configuration before any login (registration, metadata exchange)
 */
export type StepChannel = 'front' | 'back' | 'local' | 'setup'

export interface FlowStep {
  id: string
  from: string
  /** Same as `from` for local steps. */
  to: string
  channel: StepChannel
  /** Short arrow label, e.g. "302 → /authorize". */
  label: string
  title: string
  summary: string
  details?: string[]
  /** An example HTTP message, shown verbatim. */
  http?: string
  /** What the receiving party must verify at this step. */
  checks?: string[]
  /** Id of a threat in the protocol's security list that this step defends against. */
  threats?: string[]
}

export interface FlowSpec {
  id: string
  title: string
  description: string
  lanes: Lane[]
  steps: FlowStep[]
}

export interface Component {
  term: string
  /** Other names you will meet in docs and products. */
  aka?: string[]
  /** The lab actor or artifact playing this part. */
  inLab: string
  description: string
}

export interface Threat {
  id: string
  name: string
  attack: string
  defense: string
  /** Planned as a hands-on Attack Lab toggle. */
  attackLab?: boolean
}

export type ResourceKind = 'spec' | 'guide' | 'video' | 'security'

export interface Resource {
  title: string
  url: string
  kind: ResourceKind
  source: string
  note: string
}

export interface ProtocolSpec {
  slug: string
  name: string
  shortName: string
  tagline: string
  /** Quick facts for the overview, e.g. { label: 'Format', value: 'JSON, JWT' }. */
  facts: { label: string; value: string }[]
  playgroundStatus: string
  overview: {
    whatItIs: string[]
    useWhen: string[]
    avoidWhen: string[]
  }
  components: Component[]
  artifacts: Component[]
  flow: FlowSpec
  threats: Threat[]
  resources: Resource[]
}
