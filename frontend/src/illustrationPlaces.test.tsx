import { act, cleanup, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api/index.ts'
import { renderRoute } from './test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from './test/session.ts'
import { setViewport } from './test/viewport.ts'

// §9 Design, #77: the three drawings show only on the login, registration, entries and
// review pages. Every other page, and the app shell, has none. The pages that have one are
// tested in their own test files.

vi.mock('./api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/index.ts')>()
  return { ...actual, listEntries: vi.fn(), getEntry: vi.fn(), listTags: vi.fn() }
})

const ENTRY: api.Entry = {
  id: '42',
  date: '2026-11-10',
  text: 'Led the incident review.',
  category: 'Achievement',
  tags: [],
  result_impact: null,
  created_at: '2026-11-10T09:00:00Z',
  updated_at: '2026-11-10T09:00:00Z',
}

function illustrations(): Element[] {
  return Array.from(document.querySelectorAll('svg.illustration, .empty-state__illustration'))
}

async function renderAt(path: string): Promise<void> {
  renderRoute(path)
  await act(async () => {})
}

beforeEach(() => {
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [] })
  vi.mocked(api.getEntry).mockResolvedValue(ENTRY)
  vi.mocked(api.listTags).mockResolvedValue({ tags: [] })
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('pages without an illustration (§9 Design)', () => {
  it.each([
    ['/entries/new', 'New entry'],
    ['/entries/42/edit', 'Edit entry'],
    ['/summaries', 'Summaries'],
    ['/summaries/42', 'Summary'],
    ['/settings', 'Settings'],
    ['/does-not-exist', 'Page not found'],
  ])('test_design_%s_shows_no_illustration_in_the_app_shell', async (path, heading) => {
    storeTestSession()
    for (const width of ['phone', 'laptop'] as const) {
      setViewport(width)
      await renderAt(path)

      expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
      expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
      expect(illustrations()).toEqual([])
      cleanup()
    }
  })

  it('test_design_page_not_found_logged_out_shows_no_illustration', async () => {
    await renderAt('/does-not-exist')

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
    // The login layout without the app navigation, but without the login drawing.
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(document.querySelector('.wordmark')).not.toBeNull()
    expect(illustrations()).toEqual([])
  })
})
