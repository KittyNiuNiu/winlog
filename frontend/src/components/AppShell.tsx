import { Link, NavLink, Outlet } from 'react-router'
import './AppShell.css'

const NAV_LINKS = [
  { to: '/', label: 'Entries', end: true },
  { to: '/review', label: 'Review', end: false },
  { to: '/summaries', label: 'Summaries', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

// The frame around every page except login and register: the product name and the
// main navigation. Mobile first: a top bar on small screens, a sidebar on wide ones.
export default function AppShell() {
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
      </header>
      <main className="shell__main" id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
