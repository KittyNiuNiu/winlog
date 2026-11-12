import { FileText, ListFilter, NotebookText, Settings, type LucideIcon } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link, Outlet, matchPath, useLocation, useNavigate } from 'react-router'
import { logout } from '../api/index.ts'
import { ButtonLink } from './Button.tsx'
import Icon from './Icon.tsx'
import { LAPTOP_QUERY, useMediaQuery } from './useMediaQuery.ts'
import Wordmark from './Wordmark.tsx'
import './AppShell.css'

type SectionKey = 'entries' | 'review' | 'summaries' | 'settings'

interface Section {
  key: SectionKey
  to: string
  label: string
  icon: LucideIcon
  /** The pages on which this section is the current one. */
  paths: string[]
}

const SECTIONS: Section[] = [
  { key: 'entries', to: '/', label: 'Entries', icon: NotebookText, paths: ['/', '/entries/new', '/entries/:id/edit'] },
  { key: 'review', to: '/review', label: 'Review', icon: ListFilter, paths: ['/review'] },
  { key: 'summaries', to: '/summaries', label: 'Summaries', icon: FileText, paths: ['/summaries', '/summaries/:id'] },
  { key: 'settings', to: '/settings', label: 'Settings', icon: Settings, paths: ['/settings'] },
]

/** On the phone, these sections are in the header; the others are under More. */
const PHONE_HEADER: SectionKey[] = ['entries', 'review']

/** The section of the page at `pathname`, or null (for example on "Page not found"). */
function currentSection(pathname: string): SectionKey | null {
  const section = SECTIONS.find(({ paths }) => paths.some((path) => matchPath({ path, end: true }, pathname)))
  return section?.key ?? null
}

interface AppShellProps {
  /** The page to show. By default, the matching child route. */
  children?: ReactNode
}

// The frame around every page except login and register. One navigation ("Main") at both
// widths, built for the width it is shown at:
// - phone (below 48rem): a header with the wordmark, Entries, Review and More; More opens
//   a menu with Summaries, Settings and Log out;
// - laptop: a sidebar with the wordmark, the four sections with icons, "New entry" and,
//   at the bottom, Log out.
export default function AppShell({ children }: AppShellProps) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const laptop = useMediaQuery(LAPTOP_QUERY)
  const [loggingOut, setLoggingOut] = useState(false)
  // The menu belongs to the page it was opened on, so it is closed on every other page.
  const [menuOpenOn, setMenuOpenOn] = useState<string | null>(null)
  const menuOpen = !laptop && menuOpenOn === pathname
  const menuId = useId()
  const moreRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const current = currentSection(pathname)

  useEffect(() => {
    if (!menuOpen) {
      return undefined
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpenOn(null)
        moreRef.current?.focus()
      }
    }
    function handlePointerDown(event: PointerEvent) {
      const target = event.target
      if (target instanceof Node && (menuRef.current?.contains(target) || moreRef.current?.contains(target))) {
        return
      }
      setMenuOpenOn(null)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handlePointerDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [menuOpen])

  function closeMenu() {
    setMenuOpenOn(null)
  }

  async function handleLogout() {
    closeMenu()
    setLoggingOut(true)
    try {
      await logout()
    } catch {
      // Nothing to show: logout removes the stored token even when the request fails (#25).
    }
    await navigate('/login', { replace: true })
  }

  function sectionLink(section: Section, className: string, onClick?: () => void) {
    const isCurrent = section.key === current
    return (
      <Link
        className={`${className}${isCurrent ? ` ${className}--current` : ''}`}
        to={section.to}
        aria-current={isCurrent ? 'page' : undefined}
        onClick={onClick}
      >
        {laptop && <Icon className="shell__row-icon" icon={section.icon} size={20} />}
        {section.label}
      </Link>
    )
  }

  const logoutButton = (className: string) => (
    <button
      className={className}
      type="button"
      onClick={() => void handleLogout()}
      disabled={loggingOut}
      aria-busy={loggingOut}
    >
      {loggingOut && <span className="spinner" aria-hidden="true" />}
      {loggingOut ? 'Logging out…' : 'Log out'}
    </button>
  )

  const moreSections = SECTIONS.filter(({ key }) => !PHONE_HEADER.includes(key))
  const moreCurrent = current !== null && !PHONE_HEADER.includes(current)

  return (
    <div className={`shell ${laptop ? 'shell--laptop' : 'shell--phone'}`}>
      <a className="shell__skip-link" href="#main">
        Skip to content
      </a>
      <header className="shell__header">
        {laptop ? (
          <nav className="shell__nav" aria-label="Main">
            <Wordmark link />
            <ul className="shell__rows">
              {SECTIONS.map((section) => (
                <li key={section.key}>{sectionLink(section, 'shell__row')}</li>
              ))}
            </ul>
            <ButtonLink className="shell__new-entry" variant="secondary" to="/entries/new">
              New entry
            </ButtonLink>
            <div className="shell__logout">{logoutButton('shell__row shell__logout-button')}</div>
          </nav>
        ) : (
          <nav className="shell__nav" aria-label="Main">
            <Wordmark link />
            <ul className="shell__pills">
              {SECTIONS.filter(({ key }) => PHONE_HEADER.includes(key)).map((section) => (
                <li key={section.key}>{sectionLink(section, 'shell__pill')}</li>
              ))}
              <li>
                <button
                  ref={moreRef}
                  className={`shell__pill${moreCurrent ? ' shell__pill--current' : ''}`}
                  type="button"
                  aria-expanded={menuOpen}
                  aria-controls={menuId}
                  onClick={() => setMenuOpenOn(menuOpen ? null : pathname)}
                >
                  More
                </button>
              </li>
            </ul>
            <div className="shell__menu" id={menuId} ref={menuRef} hidden={!menuOpen}>
              <ul className="shell__menu-list">
                {moreSections.map((section) => (
                  <li key={section.key}>{sectionLink(section, 'shell__menu-item', closeMenu)}</li>
                ))}
              </ul>
              <div className="shell__menu-separator" aria-hidden="true" />
              {logoutButton('shell__menu-item shell__logout-button')}
            </div>
          </nav>
        )}
      </header>
      <main className="shell__main" id="main" tabIndex={-1}>
        {children ?? <Outlet />}
      </main>
    </div>
  )
}
