import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { clearSession, saveSession } from '../api/session.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { entrySavedState } from '../entries/entrySavedNotice.ts'
import { routes } from '../routes.tsx'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

// The demo notice in the app shell (FR-X1, §7.7, #35). The API client is mocked: pages
// stay loading, so only the shell and the notice matter. No AI call is made.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    logout: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    listEntries: vi.fn(),
    listTags: vi.fn(),
    getEntry: vi.fn(),
    listSummaries: vi.fn(),
    getSummary: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const logout = vi.mocked(api.logout)

const NOTICE_TEXT =
  "You're using a shared demo account. Anyone can see and change this data, and AI limits are shared by everyone. Don't enter personal information."

const APP_PAGES = ['/', '/entries/new', '/entries/42/edit', '/review', '/summaries', '/summaries/42', '/settings']

function storeDemoSession(): void {
  saveSession({ token: 'demo-token', expiresAt: '2099-01-01T00:00:00Z', demo: true })
}

function notice(): HTMLElement {
  const element = document.querySelector('.demo-notice')
  if (!(element instanceof HTMLElement)) {
    throw new Error('no demo notice')
  }
  return element
}

function queryNotice(): Element | null {
  return document.querySelector('.demo-notice')
}

function createAccountLink(): HTMLAnchorElement {
  return within(notice()).getByRole('link', { name: /^(Create your own account|Leaving the demo…)$/ }) as HTMLAnchorElement
}

function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

function deferred() {
  let resolve: () => void = () => {}
  let reject: (reason: unknown) => void = () => {}
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  const loading = () => new Promise<never>(() => {})
  vi.mocked(api.listEntries).mockImplementation(loading)
  vi.mocked(api.listTags).mockImplementation(loading)
  vi.mocked(api.getEntry).mockImplementation(loading)
  vi.mocked(api.listSummaries).mockImplementation(loading)
  vi.mocked(api.getSummary).mockImplementation(loading)
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('the demo notice on app pages (FR-X1)', () => {
  describe.each(['phone', 'laptop'] as const)('at %s width', (width) => {
    beforeEach(() => {
      setViewport(width)
    })

    it.each([...APP_PAGES, '/does-not-exist'])('test_fr_x1_demo_notice_on_%s', (path) => {
      storeDemoSession()
      renderRoute(path)

      const element = notice()
      expect(element.querySelector('p')?.textContent).toBe(NOTICE_TEXT)
      expect(createAccountLink().textContent).toBe('Create your own account')
      expect(createAccountLink().getAttribute('href')).toBe('/register')
      // First in the main content area, before the page's own content.
      const main = screen.getByRole('main')
      expect(main.firstElementChild).toBe(element)
      const heading = within(main).getByRole('heading', { level: 1 })
      expect(element.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      // It cannot be closed: no button in it.
      expect(within(element).queryByRole('button')).toBeNull()
    })
  })

  it('test_fr_x1_demo_notice_on_page_not_found_while_logged_in', () => {
    storeDemoSession()
    renderRoute('/summaries/42/extra')

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
    expect(screen.getByRole('main').firstElementChild).toBe(notice())
  })

  it('test_fr_x1_demo_notice_is_not_a_live_region_and_skip_to_content_reaches_it', () => {
    storeDemoSession()
    renderRoute('/')

    const element = notice()
    expect(element.getAttribute('role')).toBeNull()
    expect(element.getAttribute('aria-live')).toBeNull()
    expect(element.closest('[role="status"], [role="alert"], [aria-live]')).toBeNull()
    expect(within(element).queryAllByRole('status')).toHaveLength(0)
    expect(within(element).queryAllByRole('alert')).toHaveLength(0)
    // The information look with its icon, hidden from screen readers.
    expect(element.classList.contains('message--info')).toBe(true)
    expect(element.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    // Inside <main id="main">, the target of "Skip to content".
    expect(screen.getByRole('link', { name: 'Skip to content' }).getAttribute('href')).toBe('#main')
    expect(screen.getByRole('main').contains(element)).toBe(true)
  })

  it('test_fr_x1_demo_notice_sits_above_the_entry_saved_band', async () => {
    storeDemoSession()
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [] })
    const router = createMemoryRouter(routes, { initialEntries: [{ pathname: '/', state: entrySavedState() }] })
    connectLoginRedirect(router)
    render(<RouterProvider router={router} />)
    await act(async () => {})

    const saved = screen.getByText('Entry saved.')
    expect(notice().compareDocumentPosition(saved) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(notice().contains(saved)).toBe(false)
  })

  it('test_fr_x1_demo_notice_stays_on_page_changes', async () => {
    storeDemoSession()
    const { router } = renderRoute('/')

    for (const path of ['/review', '/summaries', '/settings', '/']) {
      await act(async () => {
        await router.navigate(path)
      })
      expect(screen.getByRole('main').firstElementChild).toBe(notice())
    }
  })

  it('test_fr_x1_demo_notice_after_a_reload_from_the_stored_session', async () => {
    storeDemoSession()
    expect(JSON.parse(localStorage.getItem('winlog.session') ?? 'null')).toEqual({
      token: 'demo-token',
      expiresAt: '2099-01-01T00:00:00Z',
      demo: true,
    })
    // As after a reload: fresh modules, so the session is read from localStorage again.
    vi.resetModules()
    const freshApi = await import('../api/index.ts')
    const { renderRoute: renderFresh } = await import('../test/renderRoute.tsx')
    vi.mocked(freshApi.listEntries).mockImplementation(() => new Promise<never>(() => {}))

    renderFresh('/')

    expect(freshApi.getSession()?.demo).toBe(true)
    expect(notice().querySelector('p')?.textContent).toBe(NOTICE_TEXT)
  })
})

describe('no demo notice for other sessions (FR-X1)', () => {
  it.each([...APP_PAGES, '/does-not-exist'])('test_fr_x1_no_demo_notice_for_a_normal_session_on_%s', (path) => {
    // As after "Log in" or registration: demo is false.
    storeTestSession()
    renderRoute(path)

    expect(screen.getByRole('main')).toBeTruthy()
    expect(queryNotice()).toBeNull()
    expect(screen.queryByText(NOTICE_TEXT)).toBeNull()
    expect(screen.queryByRole('link', { name: 'Create your own account' })).toBeNull()
  })

  it('test_fr_x1_no_demo_notice_when_logged_out', () => {
    renderRoute('/does-not-exist')

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
    expect(queryNotice()).toBeNull()
  })

  it('test_fr_x1_demo_notice_goes_after_log_out', async () => {
    setViewport('laptop')
    logout.mockImplementation(async () => {
      clearSession()
    })
    storeDemoSession()
    const { router } = renderRoute('/')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(queryNotice()).toBeNull()
    expect(api.getSession()).toBeNull()
  })

  it('test_fr_x1_demo_notice_goes_when_the_session_ends', async () => {
    storeDemoSession()
    const { router } = renderRoute('/review')
    expect(queryNotice()).not.toBeNull()
    // As the client does on a 401: remove the session, then call the redirect.
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(queryNotice()).toBeNull()
  })

  it('test_fr_x1_demo_notice_goes_when_the_token_expires', async () => {
    saveSession({ token: 'demo-token', expiresAt: new Date(Date.now() + 60_000).toISOString(), demo: true })
    const { router } = renderRoute('/review')
    expect(queryNotice()).not.toBeNull()
    saveSession({ token: 'demo-token', expiresAt: '2000-01-01T00:00:00Z', demo: true })

    await act(async () => {
      await router.navigate('/summaries')
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(queryNotice()).toBeNull()
  })
})

describe('"Create your own account" in the demo notice (FR-X1)', () => {
  it('test_fr_x1_create_own_account_logs_out_and_opens_register', async () => {
    logout.mockImplementation(async () => {
      clearSession()
    })
    storeDemoSession()
    const { router } = renderRoute('/review')

    await act(async () => {
      fireEvent.click(createAccountLink())
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(api.getSession()).toBeNull()
    expect(router.state.location.pathname).toBe('/register')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(screen.getByRole('heading', { level: 1, name: 'Create an account' })).toBeTruthy()
    expect(queryNotice()).toBeNull()
  })

  it('test_fr_x1_create_own_account_opens_register_when_logout_fails', async () => {
    // Like the real client: the stored session is removed even though the request fails.
    logout.mockImplementation(async () => {
      clearSession()
      throw new api.NetworkError()
    })
    storeDemoSession()
    const { router } = renderRoute('/')

    await act(async () => {
      fireEvent.click(createAccountLink())
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(api.getSession()).toBeNull()
    expect(router.state.location.pathname).toBe('/register')
    expect(screen.queryByText(/Can't reach Winlog/)).toBeNull()
    expect(queryNotice()).toBeNull()
  })

  it('test_fr_x1_create_own_account_is_busy_and_a_second_press_does_nothing', async () => {
    const request = deferred()
    logout.mockImplementation(async () => {
      try {
        await request.promise
      } finally {
        clearSession()
      }
    })
    storeDemoSession()
    const { router } = renderRoute('/settings')

    await act(async () => {
      fireEvent.click(createAccountLink())
    })

    const link = createAccountLink()
    expect(link.textContent).toBe('Leaving the demo…')
    expect(link.querySelector('.spinner')?.getAttribute('aria-hidden')).toBe('true')
    expect(link.getAttribute('aria-disabled')).toBe('true')
    expect(link.classList.contains('demo-notice__link--busy')).toBe(true)
    await act(async () => {
      fireEvent.click(link)
    })
    expect(logout).toHaveBeenCalledTimes(1)
    expect(router.state.location.pathname).toBe('/settings')

    await act(async () => {
      request.resolve()
    })

    expect(logout).toHaveBeenCalledTimes(1)
    expect(router.state.location.pathname).toBe('/register')
  })

  it('test_fr_x1_log_out_and_create_own_account_do_not_run_together', async () => {
    setViewport('laptop')
    const request = deferred()
    logout.mockImplementation(async () => {
      await request.promise
      clearSession()
    })
    storeDemoSession()
    const { router } = renderRoute('/')

    await act(async () => {
      fireEvent.click(createAccountLink())
    })
    const logOutButton = screen.getByRole('button', { name: 'Log out' }) as HTMLButtonElement
    expect(logOutButton.disabled).toBe(true)
    await act(async () => {
      fireEvent.click(logOutButton)
    })
    expect(logout).toHaveBeenCalledTimes(1)

    await act(async () => {
      request.resolve()
    })
    expect(router.state.location.pathname).toBe('/register')
  })
})
