import { act, fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderRoute } from './test/renderRoute.tsx'

const SHELL_PAGES = [
  ['/', 'Entries'],
  ['/review', 'Review'],
  ['/summaries', 'Summaries'],
  ['/summaries/42', 'Summary'],
  ['/settings', 'Settings'],
]

const AUTH_PAGES = [
  ['/login', 'Log in'],
  ['/register', 'Register'],
]

describe('routes', () => {
  it.each(SHELL_PAGES)('%s shows its placeholder page inside the app shell', (path, heading) => {
    renderRoute(path)

    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
    expect(screen.getByRole('main').contains(screen.getByRole('heading', { level: 1 }))).toBe(
      true,
    )
  })

  it.each(AUTH_PAGES)('%s shows its placeholder page without the app shell', (path, heading) => {
    renderRoute(path)

    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(screen.queryByRole('navigation')).toBeNull()
    for (const name of ['Entries', 'Review', 'Summaries', 'Settings']) {
      expect(screen.queryByRole('link', { name })).toBeNull()
    }
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
