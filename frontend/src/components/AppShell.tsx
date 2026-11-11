import { useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { logout } from '../api/index.ts'
import './AppShell.css'

const NAV_LINKS = [
  { to: '/', label: 'Entries', end: true },
  { to: '/review', label: 'Review', end: false },
  { to: '/summaries', label: 'Summaries', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

interface AppShellProps {
  /** The page to show. By default, the matching child route. */
  children?: ReactNode
}

// The frame around every page except login and register: the product name, the main
// navigation and "Log out". Mobile first: a top bar on small screens, a sidebar on wide
// ones.
export default function AppShell({ children }: AppShellProps) {
  const navigate = useNavigate()
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await logout()
    } catch {
      // Nothing to show: logout removes the stored token even when the request fails (#25).
    }
    await navigate('/login', { replace: true })
  }

  return (
    <div className="shell">
      <a className="shell__skip-link" href="#main">
        Skip to content
      </a>
      <header className="shell__header">
        <Link className="shell__brand" to="/">
          Winlog
        </Link>
        <nav className="shell__nav" aria-label="Main">
          <ul className="shell__nav-list">
            {NAV_LINKS.map((link) => (
              <li key={link.to}>
                <NavLink className="shell__nav-link" to={link.to} end={link.end}>
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <button
          className="shell__logout"
          type="button"
          onClick={() => void handleLogout()}
          disabled={loggingOut}
          aria-busy={loggingOut}
        >
          {loggingOut ? 'Logging out…' : 'Log out'}
        </button>
      </header>
      <main className="shell__main" id="main" tabIndex={-1}>
        {children ?? <Outlet />}
      </main>
    </div>
  )
}
