import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { clearSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'

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

function mainNav() {
  return screen.getByRole('navigation', { name: 'Main' })
}

beforeEach(() => {
  storeTestSession()
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('app shell', () => {
  it('shows the name Winlog and the four navigation links', () => {
    renderRoute('/')

    expect(screen.getByRole('link', { name: 'Winlog' }).getAttribute('href')).toBe('/')
    const links = within(mainNav()).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(NAV_LINKS.map((link) => link.name))
    for (const { name, href } of NAV_LINKS) {
      expect(within(mainNav()).getByRole('link', { name }).getAttribute('href')).toBe(href)
    }
  })

  it.each([
    ['/', 'Entries'],
    ['/review', 'Review'],
    ['/summaries', 'Summaries'],
    ['/summaries/123', 'Summaries'],
    ['/settings', 'Settings'],
  ])('marks the current section at %s', (path, current) => {
    renderRoute(path)

    for (const { name } of NAV_LINKS) {
      const link = within(mainNav()).getByRole('link', { name })
      expect(link.getAttribute('aria-current')).toBe(name === current ? 'page' : null)
    }
  })
})

describe('log out (FR-A2)', () => {
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
