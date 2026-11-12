import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { DEV_PREVIEW_PATH, createRoutes } from './routes.tsx'
import { renderRoute } from './test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from './test/session.ts'
import { setViewport } from './test/viewport.ts'

const SHELL_PAGES = [
  ['/', 'Entries'],
  ['/entries/new', 'New entry'],
  ['/entries/42/edit', 'Edit entry'],
  ['/review', 'Review'],
  ['/summaries', 'Summaries'],
  ['/summaries/42', 'Summary'],
  ['/settings', 'Settings'],
]

const AUTH_PAGES = [
  ['/login', 'Log in'],
  ['/register', 'Create an account'],
]

// Route protection itself is tested in auth/routeProtection.test.tsx.
describe('routes, logged in', () => {
  beforeEach(() => {
    storeTestSession()
  })

  afterEach(() => {
    removeTestSession()
  })

  it.each(SHELL_PAGES)('%s shows its placeholder page inside the app shell', (path, heading) => {
    renderRoute(path)

    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
    expect(screen.getByRole('main').contains(screen.getByRole('heading', { level: 1 }))).toBe(
      true,
    )
  })

  it.each(['/does-not-exist', '/summaries/42/extra', '/login/extra', '/Review-typo'])(
    'an unknown path (%s) shows "Page not found" with a link to /',
    (path) => {
      renderRoute(path)

      expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
      const main = screen.getByRole('main')
      expect(within(main).getByRole('link', { name: 'Go to your entries' }).getAttribute('href')).toBe(
        '/',
      )
      expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
    },
  )

  it('navigates on the client when a navigation link is clicked', async () => {
    setViewport('laptop')
    const { router } = renderRoute('/')
    const nav = screen.getByRole('navigation', { name: 'Main' })

    await act(async () => {
      fireEvent.click(within(nav).getByRole('link', { name: 'Summaries' }))
    })

    expect(router.state.location.pathname).toBe('/summaries')
    expect(screen.getByRole('heading', { level: 1, name: 'Summaries' })).toBeTruthy()
  })

  it('the "Page not found" link leads back to the entries page', async () => {
    const { router } = renderRoute('/nowhere')

    await act(async () => {
      fireEvent.click(screen.getByRole('link', { name: 'Go to your entries' }))
    })

    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
  })
})

describe('routes, logged out', () => {
  afterEach(() => {
    removeTestSession()
  })

  it.each(AUTH_PAGES)('%s shows its page without the app shell', (path, heading) => {
    renderRoute(path)

    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(screen.queryByRole('navigation')).toBeNull()
    for (const name of ['Entries', 'Review', 'Summaries', 'Settings']) {
      expect(screen.queryByRole('link', { name })).toBeNull()
    }
  })
})

describe('the development-only component preview', () => {
  afterEach(() => {
    removeTestSession()
  })

  it.each([
    ['logged out', false],
    ['logged in', true],
  ])('opens with npm run dev (%s), without the app shell', async (_case, loggedIn) => {
    if (loggedIn) {
      storeTestSession()
    }
    const { router } = renderRoute(DEV_PREVIEW_PATH)

    expect(await screen.findByRole('heading', { level: 1, name: 'Component preview' })).toBeTruthy()
    expect(router.state.location.pathname).toBe(DEV_PREVIEW_PATH)
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull()
  })

  it('is "Page not found" in the production build, which has no development routes', () => {
    const router = createMemoryRouter(createRoutes([]), { initialEntries: [DEV_PREVIEW_PATH] })
    render(<RouterProvider router={router} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Component preview' })).toBeNull()
  })
})
