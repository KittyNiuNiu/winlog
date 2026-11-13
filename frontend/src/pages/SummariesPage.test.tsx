import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { NetworkError, UnknownError, type Summary, type SummaryFilter } from '../api/index.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { routes } from '../routes.tsx'
import { summaryDeletedState } from '../summaries/summaryDeletedNotice.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

// The summaries list (#33): every saved summary, newest first, each row one link to its
// page (FR-R4), and the one-time messages after a delete (FR-R5). The API client is
// mocked; these pages make no AI call. Tests run in Sydney (vite.config.ts).

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    listSummaries: vi.fn(),
    getSummary: vi.fn(),
    listEntries: vi.fn(),
    listTags: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const listSummaries = vi.mocked(api.listSummaries)

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const EMPTY_TEXT = 'No summaries yet. Draft one on the Review page.'

const HALF_YEAR: SummaryFilter = { period_start: '2026-01-01', period_end: '2026-06-30' }

function makeSummary(id: string, overrides: Partial<Summary> = {}): Summary {
  return {
    id,
    text: `Summary ${id}`,
    filter: HALF_YEAR,
    created_at: '2026-11-13T09:00:00Z',
    updated_at: '2026-11-13T09:00:00Z',
    ...overrides,
  }
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {}
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

async function flush(): Promise<void> {
  await act(async () => {})
}

async function renderList(path = '/summaries') {
  const result = renderRoute(path)
  await flush()
  return result
}

/** Opens /summaries with a navigation state, as the summary page does after a delete. */
async function renderWithState(state: unknown) {
  const router = createMemoryRouter(routes, {
    initialEntries: [{ pathname: '/summaries', state }],
  })
  connectLoginRedirect(router)
  render(<RouterProvider router={router} />)
  await flush()
  return { router }
}

function rows(): HTMLAnchorElement[] {
  return Array.from(document.querySelectorAll<HTMLAnchorElement>('.summaries-page__list a'))
}

function title(): HTMLElement {
  return screen.getByRole('heading', { level: 1, name: 'Summaries' })
}

function savedBand(): string {
  return document.querySelector('.summaries-page > .saved-region')?.textContent ?? ''
}

function goneNotice(): string {
  return document.querySelector('.summaries-page__notice')?.textContent ?? ''
}

function primaryButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('.button--primary'))
}

/** Summaries is the current section: its sidebar row on the laptop, "More" on the phone. */
function expectSummariesCurrent(width: 'phone' | 'laptop'): void {
  const nav = screen.getByRole('navigation', { name: 'Main' })
  if (width === 'laptop') {
    expect(within(nav).getByRole('link', { name: 'Summaries' }).getAttribute('aria-current')).toBe('page')
  } else {
    expect(within(nav).getByRole('button', { name: 'More' }).classList.contains('shell__pill--current')).toBe(true)
  }
}

/** The redirect the API client calls after a "not authenticated" response. */
function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

beforeEach(() => {
  storeTestSession()
  listSummaries.mockResolvedValue({ summaries: [makeSummary('s1')] })
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [] })
  vi.mocked(api.listTags).mockResolvedValue({ tags: [] })
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('the summaries list (FR-R4)', () => {
  it('test_fr_r4_list_keeps_the_order_the_server_sends', async () => {
    listSummaries.mockResolvedValue({
      summaries: [
        makeSummary('newest', { created_at: '2026-11-13T09:00:00Z' }),
        makeSummary('middle', { created_at: '2026-11-12T09:00:00Z' }),
        // Out of order on purpose: the app does not sort again.
        makeSummary('oldest', { created_at: '2026-11-14T09:00:00Z' }),
      ],
    })

    await renderList()

    expect(title()).toBeTruthy()
    expect(listSummaries).toHaveBeenCalledTimes(1)
    expect(rows().map((row) => row.getAttribute('href'))).toEqual([
      '/summaries/newest',
      '/summaries/middle',
      '/summaries/oldest',
    ])
  })

  it('test_fr_r4_list_shows_summary_filter', async () => {
    listSummaries.mockResolvedValue({
      summaries: [
        makeSummary('chosen', {
          filter: { ...HALF_YEAR, categories: ['Learning', 'Achievement'], tags: ['python', 'Leadership'] },
        }),
        makeSummary('none', { filter: HALF_YEAR }),
        makeSummary('categories', { filter: { ...HALF_YEAR, categories: ['Achievement', 'Learning'] } }),
      ],
    })

    await renderList()

    const filters = rows().map((row) => row.querySelector('.summary-row__filter')?.textContent)
    expect(filters).toEqual([
      '1 Jan 2026 – 30 Jun 2026 · Achievement, Learning · python, Leadership',
      '1 Jan 2026 – 30 Jun 2026 · All categories · All tags',
      '1 Jan 2026 – 30 Jun 2026 · Achievement, Learning · All tags',
    ])
  })

  it('test_fr_r4_period_dates_are_shown_as_stored_and_not_shifted', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    // There, new Date('2026-01-01') is still 31 December; the stored text must be used.
    expect(new Date('2026-01-01').getDate()).toBe(31)
    listSummaries.mockResolvedValue({
      summaries: [makeSummary('s1', { filter: { period_start: '2026-01-01', period_end: '2026-12-31' } })],
    })

    await renderList()

    expect(rows()[0].querySelector('.summary-row__filter')?.textContent).toBe(
      '1 Jan 2026 – 31 Dec 2026 · All categories · All tags',
    )
  })

  it('test_fr_r4_creation_date_is_the_local_date_near_midnight_utc', async () => {
    // 09:30 on 13 November in Sydney, still 12 November in UTC.
    listSummaries.mockResolvedValue({ summaries: [makeSummary('s1', { created_at: '2026-11-12T22:30:00Z' })] })

    await renderList()

    const time = rows()[0].querySelector('time') as HTMLTimeElement
    expect(time.textContent).toBe('13 Nov 2026')
    expect(time.getAttribute('datetime')).toBe('2026-11-12T22:30:00Z')
    // Two lines: "13 Nov" over "2026".
    expect(time.querySelector('.summary-row__year')?.textContent).toBe('2026')
  })

  it('test_fr_r4_creation_date_in_a_time_zone_behind_utc', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    listSummaries.mockResolvedValue({ summaries: [makeSummary('s1', { created_at: '2026-01-01T03:00:00Z' })] })

    await renderList()

    expect(rows()[0].querySelector('time')?.textContent).toBe('31 Dec 2025')
  })

  it('test_fr_r4_preview_shows_the_start_of_the_text_with_line_breaks_as_spaces', async () => {
    listSummaries.mockResolvedValue({
      summaries: [makeSummary('s1', { text: 'Mock summary\n\nLed the incident review.\n  Shipped the export.\t' })],
    })

    await renderList()

    const preview = rows()[0].querySelector('.summary-row__preview') as HTMLElement
    expect(preview.textContent).toBe('Mock summary Led the incident review. Shipped the export.')
  })

  it('test_fr_r4_a_long_preview_is_cut_with_an_ellipsis', async () => {
    const long = `${'word '.repeat(100)}end`
    listSummaries.mockResolvedValue({ summaries: [makeSummary('s1', { text: long })] })

    await renderList()

    const preview = rows()[0].querySelector('.summary-row__preview')?.textContent ?? ''
    expect(preview.endsWith('…')).toBe(true)
    expect(preview.length).toBeLessThanOrEqual(241)
    expect(long.replace(/\s+/g, ' ').startsWith(preview.slice(0, -1))).toBe(true)
  })

  it('test_fr_r4_the_whole_row_is_one_link_to_the_summary_page', async () => {
    listSummaries.mockResolvedValue({
      summaries: [makeSummary('s1', { text: 'Led the review.', created_at: '2026-11-12T22:30:00Z' })],
    })
    const { router } = await renderList()

    const row = rows()[0]
    expect(row.classList.contains('summary-row')).toBe(true)
    expect(row.parentElement?.tagName).toBe('LI')
    // Date, filter line and preview are all inside the one link, with nothing else to press.
    expect(row.textContent).toBe('13 Nov 2026' + '1 Jan 2026 – 30 Jun 2026 · All categories · All tags' + 'Led the review.')
    expect(row.querySelectorAll('a, button, input, textarea')).toHaveLength(0)
    expect(row.closest('li')?.querySelectorAll('a, button')).toHaveLength(1)

    await act(async () => {
      fireEvent.click(row)
    })

    expect(router.state.location.pathname).toBe('/summaries/s1')
  })

  it('test_fr_r4_no_plum_fill_on_a_list_with_summaries', async () => {
    await renderList()

    expect(primaryButtons()).toEqual([])
  })

  it.each(['phone', 'laptop'] as const)('test_fr_r4_summaries_is_current_on_the_list_%s', async (width) => {
    setViewport(width)
    await renderList()

    expectSummariesCurrent(width)
  })
})

describe('the empty list (FR-R4)', () => {
  it('test_fr_r4_empty_state_says_draft_one_on_the_review_page', async () => {
    listSummaries.mockResolvedValue({ summaries: [] })
    const { router } = await renderList()

    expect(screen.getByText(EMPTY_TEXT)).toBeTruthy()
    const action = screen.getByRole('link', { name: 'Go to Review' })
    expect(action.classList.contains('button--primary')).toBe(true)
    expect(primaryButtons()).toEqual([action])
    expect(document.querySelector('svg.illustration, .empty-state__illustration')).toBeNull()
    expect(document.querySelector('.summaries-page__list')).toBeNull()

    await act(async () => {
      fireEvent.click(action)
    })

    expect(router.state.location.pathname).toBe('/review')
  })
})

describe('after a delete (FR-R5)', () => {
  it('test_fr_r5_summary_deleted_shows_once_and_focuses_the_title', async () => {
    listSummaries.mockResolvedValue({ summaries: [makeSummary('other')] })
    const { router } = await renderWithState(summaryDeletedState('deleted'))

    expect(savedBand()).toBe('Summary deleted.')
    expect(document.querySelector('.summaries-page > .saved-region')?.getAttribute('role')).toBe('status')
    expect(goneNotice()).toBe('')
    expect(document.activeElement).toBe(title())
    expect(title().getAttribute('tabindex')).toBe('-1')
    expect(rows().map((row) => row.getAttribute('href'))).toEqual(['/summaries/other'])
    // The state is forgotten, so a reload does not show it again.
    expect(router.state.location.state).toBeNull()

    await act(async () => {
      await router.navigate('/review')
    })
    await act(async () => {
      await router.navigate('/summaries')
    })
    expect(savedBand()).toBe('')
    expect(document.activeElement).not.toBe(title())
  })

  it('test_fr_r5_summary_deleted_above_the_empty_state_after_the_last_one', async () => {
    listSummaries.mockResolvedValue({ summaries: [] })
    await renderWithState(summaryDeletedState('deleted'))

    expect(savedBand()).toBe('Summary deleted.')
    expect(screen.getByText(EMPTY_TEXT)).toBeTruthy()
    const band = document.querySelector('.summaries-page > .saved-region') as HTMLElement
    expect(band.compareDocumentPosition(title()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('test_fr_r5_summary_deleted_fades_after_its_time', async () => {
    vi.useFakeTimers()
    await renderWithState(summaryDeletedState('deleted'))
    expect(savedBand()).toBe('Summary deleted.')

    await act(async () => {
      vi.advanceTimersByTime(5_000)
    })

    expect(savedBand()).toBe('')
  })

  it('test_fr_r5_already_deleted_shows_the_information_once', async () => {
    const { router } = await renderWithState(summaryDeletedState('gone'))

    expect(goneNotice()).toBe('This summary was already deleted.')
    expect(document.querySelector('.summaries-page__notice')?.getAttribute('role')).toBe('status')
    expect(savedBand()).toBe('')
    expect(document.activeElement).toBe(title())
    expect(router.state.location.state).toBeNull()

    await act(async () => {
      await router.navigate('/review')
    })
    await act(async () => {
      await router.navigate('/summaries')
    })
    expect(goneNotice()).toBe('')
  })

  it('test_fr_r5_no_message_on_a_plain_visit', async () => {
    await renderList()

    expect(savedBand()).toBe('')
    expect(goneNotice()).toBe('')
    expect(document.activeElement).not.toBe(title())
  })

  it('test_fr_r5_messages_sit_above_the_title', async () => {
    await renderWithState(summaryDeletedState('gone'))

    const page = document.querySelector('.summaries-page') as HTMLElement
    const notice = page.querySelector('.summaries-page__notice') as HTMLElement
    expect(notice.parentElement).toBe(page)
    expect(notice.compareDocumentPosition(title()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('loading and errors (FR-R4, §12)', () => {
  it('test_fr_r4_loading_shows_progress_then_the_waking_up_hint', async () => {
    vi.useFakeTimers()
    const answer = deferred<api.SummaryList>()
    listSummaries.mockReturnValue(answer.promise)
    await renderList()

    expect(title()).toBeTruthy()
    expect(screen.getByText('Loading summaries…').getAttribute('role')).toBe('status')
    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()

    await act(async () => {
      answer.resolve({ summaries: [makeSummary('s1')] })
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    expect(screen.queryByText('Loading summaries…')).toBeNull()
    expect(rows()).toHaveLength(1)
  })

  it.each([
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['a server error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r4_a_load_error_shows_a_message_and_try_again_retries (%s)', async (_case, error, message) => {
    listSummaries.mockRejectedValueOnce(error)
    await renderList()

    expect(screen.getByRole('alert').textContent).toBe(message)
    expect(screen.queryByText('server text')).toBeNull()
    const retry = screen.getByRole('button', { name: 'Try again' })
    expect(retry.classList.contains('button--secondary')).toBe(true)

    await act(async () => {
      fireEvent.click(retry)
    })

    expect(listSummaries).toHaveBeenCalledTimes(2)
    expect(rows()).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('test_fr_r4_an_expired_login_opens_the_login_page', async () => {
    const answer = deferred<api.SummaryList>()
    listSummaries.mockReturnValue(answer.promise)
    const { router } = await renderList()
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: '/summaries' })
  })
})
