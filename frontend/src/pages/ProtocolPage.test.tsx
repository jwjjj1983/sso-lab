import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { HomePage } from './HomePage'
import { ProtocolPage } from './ProtocolPage'

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/protocols/:slug/:tab?" element={<ProtocolPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtocolPage', () => {
  it('shows the overview by default, with all six sections in the tab bar', () => {
    renderAt('/protocols/oidc')
    expect(screen.getByRole('heading', { level: 1, name: 'OpenID Connect' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: /openid connect sections/i })
    expect(nav.querySelectorAll('a')).toHaveLength(6)
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('At a glance')).toBeInTheDocument()
  })

  it('shows the threats on the security tab, linked back to the steps that stop them', () => {
    renderAt('/protocols/oidc/security')
    expect(screen.getByRole('heading', { name: /login csrf/i })).toBeInTheDocument()
    const stepLink = screen.getByRole('link', { name: /The browser delivers the code to App A/ })
    expect(stepLink).toHaveAttribute('href', '/protocols/oidc/flow?step=oidc.callback')
  })

  it('lists external reading that opens safely in a new tab', () => {
    renderAt('/protocols/saml/learn')
    const link = screen.getByRole('link', { name: /A Developer's Guide to SAML/ })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('handles unknown protocols', () => {
    renderAt('/protocols/kerberos')
    expect(screen.getByText(/no such protocol/i)).toBeInTheDocument()
  })
})

describe('HomePage', () => {
  it('links to every protocol page', () => {
    renderAt('/')
    expect(screen.getByRole('link', { name: /OIDC OpenID Connect/ })).toHaveAttribute('href', '/protocols/oidc')
    expect(screen.getByRole('link', { name: /SAML SAML 2\.0/ })).toHaveAttribute('href', '/protocols/saml')
  })
})
