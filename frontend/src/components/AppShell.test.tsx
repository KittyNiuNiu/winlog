import { act, fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { clearSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, logout: vi.fn() }
})

const logout = vi.mocked(api.logout)

const NAV_LINKS = [
  { name: 'Entries', href: '/' },
  { name: 'Review', href: '/review' },
  { name: 'Summaries', href: '/summaries' },
  { name: 'Settings', href: '/settings' },
]

// Where each section is current, and the pages on which none is ("Page not found").
const CURRENT_SECTION: [string, string | null][] = [
  ['/', 'Entries'],
  ['/entries/new', 'Entries'],
  ['/review', 'Review'],
  ['/summaries', 'Summaries'],
  ['/summaries/123', 'Summaries'],
  ['/settings', 'Settings'],
  ['/does-not-exist', null],
  ['/summaries/123/extra', null],
]

function mainNav() {
  return screen.getByRole('navigation', { name: 'Main' })
}

function moreButton() {
  return within(mainNav()).getByRole('button', { name: 'More' })
}

function openMore() {
  fireEvent.click(moreButton())
}

beforeEach(() => {
  storeTestSession()
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('app shell on the laptop', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('shows the wordmark, the four sections with icons, "New entry" and Log out', () => {
    renderRoute('/')

    expect(within(mainNav()).getByRole('link', { name: 'Winlog' }).getAttribute('href')).toBe('/')
    const sections = within(mainNav()).getAllByRole('listitem').map((item) => within(item).getByRole('link'))
    expect(sections.map((link) => link.textContent)).toEqual(NAV_LINKS.map((link) => link.name))
    for (const { name, href } of NAV_LINKS) {
      const link = within(mainNav()).getByRole('link', { name })
      expect(link.getAttribute('href')).toBe(href)
      // The icon is next to a visible label, so screen readers skip it.
      const icon = link.querySelector('svg')
      expect(icon?.getAttribute('aria-hidden')).toBe('true')
    }
    expect(within(mainNav()).getByRole('link', { name: 'New entry' }).getAttribute('href')).toBe('/entries/new')
    expect(within(mainNav()).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'More' })).toBeNull()
  })

  it.each(CURRENT_SECTION)('marks the current section at %s', (path, current) => {
    renderRoute(path)

    for (const { name } of NAV_LINKS) {
      const link = within(mainNav()).getByRole('link', { name })
      expect(link.getAttribute('aria-current')).toBe(name === current ? 'page' : null)
    }
    expect(within(mainNav()).getByRole('link', { name: 'New entry' }).getAttribute('aria-current')).toBeNull()
  })

  it('"New entry" opens the New entry placeholder', async () => {
    const { router } = renderRoute('/review')

    await act(async () => {
      fireEvent.click(within(mainNav()).getByRole('link', { name: 'New entry' }))
    })

    expect(router.state.location.pathname).toBe('/entries/new')
    expect(screen.getByRole('heading', { level: 1, name: 'New entry' })).toBeTruthy()
    expect(within(mainNav()).getByRole('link', { name: 'Entries' }).getAttribute('aria-current')).toBe('page')
  })

  it('Tab reaches the skip link, the navigation and Log out in visual order', async () => {
    const user = userEvent.setup()
    renderRoute('/')

    const names: string[] = []
    for (let step = 0; step < 8; step += 1) {
      await user.tab()
      names.push(document.activeElement?.textContent ?? '')
    }

    expect(names).toEqual([
      'Skip to content',
      'Winlog',
      'Entries',
      'Review',
      'Summaries',
      'Settings',
      'New entry',
      'Log out',
    ])
  })
})

describe('app shell on the phone', () => {
  it('shows the wordmark, Entries, Review and More; the rest is under More', () => {
    renderRoute('/')

    expect(within(mainNav()).getByRole('link', { name: 'Winlog' }).getAttribute('href')).toBe('/')
    expect(within(mainNav()).getByRole('link', { name: 'Entries' }).getAttribute('href')).toBe('/')
    expect(within(mainNav()).getByRole('link', { name: 'Review' }).getAttribute('href')).toBe('/review')
    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('link', { name: 'Summaries' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Settings' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull()
    // No sidebar on the phone: no "New entry" and no icons.
    expect(screen.queryByRole('link', { name: 'New entry' })).toBeNull()
    expect(mainNav().querySelector('svg')).toBeNull()
  })

  it('More opens a menu with Summaries, Settings and Log out', () => {
    renderRoute('/')

    openMore()

    expect(moreButton().getAttribute('aria-expanded')).toBe('true')
    const menu = document.getElementById(moreButton().getAttribute('aria-controls') ?? '') as HTMLElement
    expect(menu.hidden).toBe(false)
    expect(within(menu).getAllByRole('link').map((link) => link.textContent)).toEqual(['Summaries', 'Settings'])
    expect(within(menu).getByRole('link', { name: 'Summaries' }).getAttribute('href')).toBe('/summaries')
    expect(within(menu).getByRole('link', { name: 'Settings' }).getAttribute('href')).toBe('/settings')
    expect(within(menu).getByRole('button', { name: 'Log out' })).toBeTruthy()
    // The menu follows More in the DOM, so Tab reaches it next.
    expect(moreButton().compareDocumentPosition(menu) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('the menu closes on Escape and focus returns to More', async () => {
    const user = userEvent.setup()
    renderRoute('/')
    await user.click(moreButton())
    await user.tab()
    expect(document.activeElement?.textContent).toBe('Summaries')

    await user.keyboard('{Escape}')

    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('link', { name: 'Summaries' })).toBeNull()
    expect(document.activeElement).toBe(moreButton())
  })

  it('the menu closes on a tap outside it', async () => {
    const user = userEvent.setup()
    renderRoute('/')
    await user.click(moreButton())

    await user.click(screen.getByRole('heading', { level: 1, name: 'Entries' }))

    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('link', { name: 'Settings' })).toBeNull()
  })

  it('the menu stays open on a tap inside it, and More closes it again', async () => {
    const user = userEvent.setup()
    renderRoute('/')
    await user.click(moreButton())
    const menu = document.getElementById(moreButton().getAttribute('aria-controls') ?? '') as HTMLElement

    await user.pointer({ keys: '[MouseLeft]', target: menu })
    expect(moreButton().getAttribute('aria-expanded')).toBe('true')

    await user.click(moreButton())
    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
  })

  it.each([
    ['Summaries', '/summaries'],
    ['Settings', '/settings'],
  ])('choosing %s opens its page and closes the menu', async (name, path) => {
    const user = userEvent.setup()
    const { router } = renderRoute('/')
    await user.click(moreButton())

    await user.click(screen.getByRole('link', { name }))

    expect(router.state.location.pathname).toBe(path)
    expect(screen.getByRole('heading', { level: 1, name })).toBeTruthy()
    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('link', { name })).toBeNull()
  })

  it.each(CURRENT_SECTION)('marks the current section at %s', (path, current) => {
    renderRoute(path)
    openMore()

    for (const { name } of NAV_LINKS) {
      const link = within(mainNav()).getByRole('link', { name })
      expect(link.getAttribute('aria-current')).toBe(name === current ? 'page' : null)
    }
    // More only looks current (on Summaries and Settings); aria-current is for links.
    const moreCurrent = current === 'Summaries' || current === 'Settings'
    expect(moreButton().classList.contains('shell__pill--current')).toBe(moreCurrent)
    expect(moreButton().getAttribute('aria-current')).toBeNull()
  })

  it('Tab reaches the skip link, the header and then the open menu in visual order', async () => {
    const user = userEvent.setup()
    renderRoute('/')

    const names: string[] = []
    for (let step = 0; step < 5; step += 1) {
      await user.tab()
      names.push(document.activeElement?.textContent ?? '')
    }
    await user.keyboard('{Enter}')
    for (let step = 0; step < 3; step += 1) {
      await user.tab()
      names.push(document.activeElement?.textContent ?? '')
    }

    expect(names).toEqual(['Skip to content', 'Winlog', 'Entries', 'Review', 'More', 'Summaries', 'Settings', 'Log out'])
  })

  it('switches to the sidebar when the window gets wider', () => {
    renderRoute('/')
    expect(screen.getByRole('button', { name: 'More' })).toBeTruthy()

    setViewport('laptop')

    expect(screen.queryByRole('button', { name: 'More' })).toBeNull()
    expect(within(mainNav()).getByRole('link', { name: 'Summaries' })).toBeTruthy()
  })
})

describe('skip to content', () => {
  it('links to the page content, which can take focus', () => {
    renderRoute('/review')

    const skip = screen.getByRole('link', { name: 'Skip to content' })
    expect(skip.getAttribute('href')).toBe('#main')
    const main = screen.getByRole('main')
    expect(main.id).toBe('main')
    expect(main.getAttribute('tabindex')).toBe('-1')
  })
})

// The #26 logout tests, on the laptop, where Log out is in the sidebar. The phone test
// below opens the More menu first.
describe('log out (FR-A2)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_a2_logout_calls_logout_and_opens_login', async () => {
    // Like the real client: the request succeeds and the stored token is removed.
    logout.mockImplementation(async () => {
      clearSession()
    })
    const { router } = renderRoute('/review')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(api.getSession()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    // Nothing remembered: after logging in again, the user starts at /.
    expect(router.state.location.state).toBeNull()
  })

  it('test_fr_a2_logout_opens_login_when_the_request_fails', async () => {
    // Like the real client: the token is removed even though the request fails (#25).
    logout.mockImplementation(async () => {
      clearSession()
      throw new api.NetworkError()
    })
    const { router } = renderRoute('/')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(api.getSession()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    expect(screen.queryByText(/Can't reach Winlog/)).toBeNull()
  })

  it('test_fr_a2_logout_button_is_disabled_while_the_request_runs', async () => {
    let finish: () => void = () => {}
    logout.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = () => {
            clearSession()
            resolve()
          }
        }),
    )
    const { router } = renderRoute('/')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    })

    const button = screen.getByRole('button', { name: 'Logging out…' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
    expect(logout).toHaveBeenCalledTimes(1)
    expect(router.state.location.pathname).toBe('/')

    await act(async () => {
      finish()
    })

    expect(router.state.location.pathname).toBe('/login')
  })
})

describe('log out on the phone (FR-A2)', () => {
  it('test_fr_a2_logout_from_the_more_menu_closes_it_and_opens_login', async () => {
    let finish: () => void = () => {}
    logout.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = () => {
            clearSession()
            resolve()
          }
        }),
    )
    const { router } = renderRoute('/settings')
    openMore()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(moreButton().getAttribute('aria-expanded')).toBe('false')
    // Opened again before the request ends: still "Logging out…", and it cannot be pressed.
    openMore()
    const button = screen.getByRole('button', { name: 'Logging out…' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
    expect(logout).toHaveBeenCalledTimes(1)

    await act(async () => {
      finish()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(api.getSession()).toBeNull()
  })
})
