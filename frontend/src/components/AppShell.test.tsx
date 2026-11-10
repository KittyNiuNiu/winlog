import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../test/renderRoute.tsx'

const NAV_LINKS = [
  { name: 'Entries', href: '/' },
  { name: 'Review', href: '/review' },
  { name: 'Summaries', href: '/summaries' },
  { name: 'Settings', href: '/settings' },
]

function mainNav() {
  return screen.getByRole('navigation', { name: 'Main' })
}

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
