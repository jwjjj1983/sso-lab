import { NavLink, Route, Routes } from 'react-router'
import { DiagnosticsPage } from './pages/DiagnosticsPage'
import { HomePage } from './pages/HomePage'

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-2 py-1 text-sm ${isActive ? 'bg-surface-2 font-medium' : 'text-muted hover:text-fg'}`
}

export function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="bg-front-bg px-4 py-1.5 text-center text-xs text-front" role="note">
        Demo only: every account here is a throwaway demo account. Never enter a real password.
      </div>
      <header className="border-b border-border bg-surface">
        <nav className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2 font-semibold">
            <img src="/favicon.svg" alt="" className="size-6" />
            SSO Lab
          </NavLink>
          <div className="ml-auto flex gap-1">
            <NavLink to="/" end className={navClass}>
              Home
            </NavLink>
            <NavLink to="/lab/diagnostics" className={navClass}>
              Diagnostics
            </NavLink>
          </div>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/lab/diagnostics" element={<DiagnosticsPage />} />
          <Route path="*" element={<p className="text-muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}
