import { useEffect } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router'
import { PROTOCOLS } from './content/protocols'
import { DiagnosticsPage } from './pages/DiagnosticsPage'
import { HomePage } from './pages/HomePage'
import { ProtocolPage } from './pages/ProtocolPage'

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-2 py-1 text-sm ${isActive ? 'bg-surface-2 font-medium' : 'text-muted hover:text-fg'}`
}

/** Scroll to the top on page changes (but not when only the query string or hash changes). */
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <ScrollToTop />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-surface focus:p-2"
      >
        Skip to content
      </a>
      <div className="bg-front-bg px-4 py-1.5 text-center text-xs text-front" role="note">
        Demo only: every account here is a throwaway demo account. Never enter a real password.
      </div>
      <header className="border-b border-border bg-surface">
        <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <img src="/favicon.svg" alt="" className="size-6" />
            SSO Lab
          </Link>
          <ul className="ml-auto flex gap-1">
            {PROTOCOLS.map((p) => (
              <li key={p.slug}>
                <NavLink to={`/protocols/${p.slug}`} className={navClass}>
                  {p.shortName}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/protocols/:slug/:tab?" element={<ProtocolPage />} />
          <Route path="/lab/diagnostics" element={<DiagnosticsPage />} />
          <Route path="*" element={<p className="text-muted">Page not found.</p>} />
        </Routes>
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap gap-x-6 gap-y-2 px-4 py-6 text-sm text-muted">
          <span>SSO Lab: a teaching playground. Demo accounts only.</span>
          <Link to="/lab/diagnostics" className="hover:text-fg">
            Lab diagnostics
          </Link>
          <a href="https://github.com/jwjjj1983/sso-lab" className="hover:text-fg" rel="noopener noreferrer">
            Source on GitHub
          </a>
        </div>
      </footer>
    </div>
  )
}
