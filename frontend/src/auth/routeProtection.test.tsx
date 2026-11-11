import { act, screen } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { connectLoginRedirect } from './loginRedirect.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, setLoginRedirect: vi.fn(actual.setLoginRedirect) }
})

const PROTECTED_PATHS = ['/', '/review', '/summaries', '/summaries/42', '/settings']

afterEach(() => {
  removeTestSession()
  vi.clearAllMocks()
})

describe('route protection without a stored token (FR-A2)', () => {
  it.each(PROTECTED_PATHS)('test_fr_a2_protected_page_%s_redirects_to_login', (path) => {
    const { router } = renderRoute(path)

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: path })
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull()
  })

  it('test_fr_a2_redirect_remembers_query_and_hash', () => {
    const { router } = renderRoute('/review?from=2026-01-01#top')

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: '/review?from=2026-01-01#top' })
  })

  it.each(['/login', '/register'])('test_fr_a2_%s_is_open_without_a_token', (path) => {
    const { router } = renderRoute(path)

    expect(router.state.location.pathname).toBe(path)
  })

  it.each(['/does-not-exist', '/login/extra'])('test_fr_a2_page_not_found_%s_is_open_without_a_token', (path) => {
    const { router } = renderRoute(path)

    expect(router.state.location.pathname).toBe(path)
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
    // Logged out: no app navigation and no "Log out".
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull()
  })

  it('test_fr_a2_expired_token_counts_as_no_token', () => {
    saveSession({ token: 'old-token', expiresAt: '2000-01-01T00:00:00Z', demo: false })

    const { router } = renderRoute('/settings')

    expect(router.state.location.pathname).toBe('/login')
  })
})

describe('route protection with a stored token (FR-A2)', () => {
  it.each(['/login', '/register'])('test_fr_a2_%s_redirects_to_entries_when_logged_in', (path) => {
    storeTestSession()

    const { router } = renderRoute(path)

    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
  })

  it.each(PROTECTED_PATHS)('test_fr_a2_protected_page_%s_opens_when_logged_in', (path) => {
    storeTestSession()

    const { router } = renderRoute(path)

    expect(router.state.location.pathname).toBe(path)
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
  })
})

describe('"not authenticated" responses (#25 login redirect hook)', () => {
  function registeredRedirect(): () => void {
    const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
    if (redirect === undefined) {
      throw new Error('setLoginRedirect was not called')
    }
    return redirect
  }

  it('test_fr_a2_not_authenticated_response_opens_login_and_remembers_the_page', async () => {
    storeTestSession()
    const { router } = renderRoute('/summaries/42?x=1')
    // As the client does on a 401: remove the session, then call the redirect.
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: '/summaries/42?x=1' })
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
  })

  it('does nothing on the login page itself', async () => {
    const router = createMemoryRouter([{ path: '*', element: null }], { initialEntries: ['/login'] })
    const navigate = vi.spyOn(router, 'navigate')
    connectLoginRedirect(router)

    await act(async () => {
      registeredRedirect()()
    })

    expect(navigate).not.toHaveBeenCalled()
  })

  it('does not remember the registration page', async () => {
    const router = createMemoryRouter([{ path: '*', element: null }], { initialEntries: ['/register'] })
    connectLoginRedirect(router)

    await act(async () => {
      registeredRedirect()()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toBeNull()
  })
})
