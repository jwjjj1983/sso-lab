import { GENERAL_RESOURCES, PROTOCOLS } from './protocols'

// Guards the content model: a typo in a lane or threat id would otherwise just render a
// broken diagram or a dead link.
describe.each(PROTOCOLS.map((p) => [p.slug, p] as const))('%s content', (slug, protocol) => {
  const { flow, threats } = protocol
  const laneIds = new Set(flow.lanes.map((l) => l.id))
  const threatIds = new Set(threats.map((t) => t.id))

  it('has unique step ids, namespaced by the protocol', () => {
    const ids = flow.steps.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) expect(id.startsWith(`${slug}.`)).toBe(true)
  })

  it('only draws arrows between lanes that exist', () => {
    for (const step of flow.steps) {
      expect(laneIds, step.id).toContain(step.from)
      expect(laneIds, step.id).toContain(step.to)
      if (step.channel === 'local') expect(step.from, step.id).toBe(step.to)
      else expect(step.from, step.id).not.toBe(step.to)
    }
  })

  it('only links to threats that exist', () => {
    for (const step of flow.steps) {
      for (const threat of step.threats ?? []) expect(threatIds, step.id).toContain(threat)
    }
  })

  it('has unique threat ids', () => {
    expect(threatIds.size).toBe(threats.length)
  })

  it('links only to https resources', () => {
    for (const r of protocol.resources) expect(r.url).toMatch(/^https:\/\//)
  })
})

it('general resources are https', () => {
  for (const r of GENERAL_RESOURCES) expect(r.url).toMatch(/^https:\/\//)
})
