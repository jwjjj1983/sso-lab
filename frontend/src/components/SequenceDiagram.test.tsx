import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { oidc } from '../content/oidc'
import { SequenceDiagram } from './SequenceDiagram'

const current = { search: '' }
function LocationSpy() {
  const { search } = useLocation()
  useEffect(() => {
    current.search = search
  }, [search])
  return null
}

function renderDiagram(initial = '/protocols/oidc/flow') {
  render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route
          path="/protocols/oidc/flow"
          element={
            <>
              <SequenceDiagram flow={oidc.flow} protocolPath="/protocols/oidc" threats={oidc.threats} />
              <LocationSpy />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

const steps = oidc.flow.steps
const tokenIndex = steps.findIndex((s) => s.id === 'oidc.token')

describe('SequenceDiagram', () => {
  it('draws every step and starts on the first', () => {
    renderDiagram()
    expect(screen.getAllByRole('button', { name: /^Step \d+:/ })).toHaveLength(steps.length)
    expect(screen.getByRole('heading', { level: 3, name: steps[0].title })).toBeInTheDocument()
  })

  it('opens the step named in the URL, so steps can be linked to', () => {
    renderDiagram('/protocols/oidc/flow?step=oidc.token')
    expect(screen.getByRole('heading', { level: 3, name: steps[tokenIndex].title })).toBeInTheDocument()
    const details = screen.getByRole('region', { name: steps[tokenIndex].title })
    expect(within(details).getByText('Back channel')).toBeInTheDocument()
    expect(within(details).getByText(/SHA-256 of/)).toBeInTheDocument()
  })

  it('selects a step on click and records it in the URL', async () => {
    renderDiagram()
    await userEvent.click(screen.getByRole('button', { name: `Step ${tokenIndex + 1}: ${steps[tokenIndex].title}` }))
    expect(screen.getByRole('heading', { level: 3, name: steps[tokenIndex].title })).toBeInTheDocument()
    expect(current.search).toBe('?step=oidc.token')
  })

  it('moves with Next / Previous and stops at the ends', async () => {
    renderDiagram()
    const previous = screen.getByRole('button', { name: /previous/i })
    expect(previous).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByRole('heading', { level: 3, name: steps[1].title })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()
  })

  it('supports arrow keys with a single tab stop (roving focus)', async () => {
    renderDiagram()
    const first = screen.getByRole('button', { name: `Step 1: ${steps[0].title}` })
    expect(first).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('button', { name: `Step 2: ${steps[1].title}` })).toHaveAttribute('tabindex', '-1')

    first.focus()
    await userEvent.keyboard('{ArrowDown}')
    const second = screen.getByRole('button', { name: `Step 2: ${steps[1].title}` })
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('aria-current', 'step')

    await userEvent.keyboard('{End}')
    expect(screen.getByRole('heading', { level: 3, name: steps[steps.length - 1].title })).toBeInTheDocument()
  })

  it('links a step to the attacks it defends against', () => {
    renderDiagram('/protocols/oidc/flow?step=oidc.callback')
    const link = screen.getByRole('link', { name: /login csrf/i })
    expect(link).toHaveAttribute('href', '/protocols/oidc/security#login-csrf')
  })
})
