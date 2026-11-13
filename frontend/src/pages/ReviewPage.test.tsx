import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import type { Entry, EntryList, EntryListQuery } from '../api/index.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { NO_TAGS_TEXT, TAGS_FAILED_TEXT, TAG_FILTER_HINT } from '../review/TagFilterField.tsx'
import { DATE_ORDER_ERROR, NO_ENTRIES_TEXT, NO_MATCH_TEXT } from '../review/reviewTexts.ts'
import { routes } from '../routes.tsx'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, listEntries: vi.fn(), listTags: vi.fn() }
})

const listEntries = vi.mocked(api.listEntries)
const listTags = vi.mocked(api.listTags)

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const KNOWN_TAGS = ['backend', 'Leadership', 'python', 'pytest']

function makeEntry(id: string, date: string, overrides: Partial<Entry> = {}): Entry {
  return {
    id,
    date,
    text: `Entry ${id}`,
    category: 'Achievement',
    tags: [],
    result_impact: null,
    created_at: `${date}T09:00:00Z`,
    updated_at: `${date}T09:00:00Z`,
    ...overrides,
  }
}

// In the API's order: newest date first, then newest created first. No side project.
function sampleEntries(): Entry[] {
  return [
    makeEntry('nov10', '2026-11-10', { category: 'Feedback' }),
    makeEntry('nov05late', '2026-11-05', { created_at: '2026-11-05T18:00:00Z', text: 'Created later' }),
    makeEntry('nov05early', '2026-11-05', { created_at: '2026-11-05T07:00:00Z', text: 'Created earlier' }),
    makeEntry('oct20', '2026-10-20', {
      category: 'Learning',
      text: 'Learned pytest fixtures.\nWrote a guide.',
      result_impact: 'The team uses it.',
      tags: ['python', 'pytest'],
    }),
    makeEntry('oct15', '2026-10-15'),
    makeEntry('nov2025', '2025-11-03'),
  ]
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {}
  let reject: (reason: unknown) => void = () => {}
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function flush(): Promise<void> {
  await act(async () => {})
}

async function renderReview(path = '/review') {
  const result = renderRoute(path)
  await flush()
  return result
}

/** Renders the app with a history, so Back and Forward can be tested. */
async function renderWithHistory(entries: string[]) {
  const router = createMemoryRouter(routes, { initialEntries: entries, initialIndex: entries.length - 1 })
  connectLoginRedirect(router)
  render(<RouterProvider router={router} />)
  await flush()
  return { router }
}

/** The query of the last `GET /entries`. */
function lastQuery(): EntryListQuery | undefined {
  return listEntries.mock.calls.at(-1)?.[0]
}

async function act_(action: () => void): Promise<void> {
  await act(async () => {
    action()
  })
}

async function click(element: HTMLElement): Promise<void> {
  await act_(() => fireEvent.click(element))
}

function categoriesGroup(): HTMLElement {
  return screen.getByRole('group', { name: 'Categories' })
}

function chip(name: string): HTMLButtonElement {
  return within(categoriesGroup()).getByRole('button', { name }) as HTMLButtonElement
}

function pressedChips(): string[] {
  return within(categoriesGroup())
    .getAllByRole('button')
    .filter((button) => button.getAttribute('aria-pressed') === 'true')
    .map((button) => button.textContent ?? '')
}

function startDate(): HTMLInputElement {
  return screen.getByLabelText('Start date') as HTMLInputElement
}

function endDate(): HTMLInputElement {
  return screen.getByLabelText('End date') as HTMLInputElement
}

async function setDate(input: HTMLInputElement, value: string): Promise<void> {
  await act_(() => fireEvent.change(input, { target: { value } }))
}

function tagInput(): HTMLInputElement {
  return screen.getByRole('combobox', { name: 'Tags' }) as HTMLInputElement
}

async function typeTag(value: string): Promise<void> {
  await act_(() => fireEvent.change(tagInput(), { target: { value } }))
}

async function key(name: string): Promise<void> {
  await act_(() => fireEvent.keyDown(tagInput(), { key: name }))
}

function offered(): string[] {
  return screen.queryAllByRole('option').map((option) => option.textContent ?? '')
}

function selectedTags(): string[] {
  const list = screen.queryByRole('list', { name: 'Selected tags' })
  return list === null ? [] : within(list).getAllByRole('listitem').map((item) => item.textContent ?? '')
}

function clearButtons(): HTMLElement[] {
  return screen.queryAllByRole('button', { name: 'Clear filters' })
}

function filtersToggle(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^Filters/ }) as HTMLButtonElement
}

function results(): HTMLElement {
  return document.querySelector('.review-page__results') as HTMLElement
}

function total(): HTMLElement {
  return document.querySelector('.review-page__total') as HTMLElement
}

function categoryHeadings(): string[] {
  return within(results())
    .queryAllByRole('heading', { level: 2 })
    .map((heading) => heading.textContent ?? '')
}

function categorySection(category: string): HTMLElement {
  return within(results()).getByRole('region', { name: new RegExp(`^${category} \\d+ entr`) })
}

function monthHeadings(section: HTMLElement): string[] {
  return within(section)
    .queryAllByRole('heading', { level: 3 })
    .map((heading) => heading.textContent ?? '')
}

function rows(container: HTMLElement = results()): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>('.entry-row'))
}

function rowTexts(container: HTMLElement = results()): string[] {
  return rows(container).map((row) => row.querySelector('.entry-row__text')?.textContent ?? '')
}

function primaryButtons(): Element[] {
  return Array.from(document.querySelectorAll('.button--primary'))
}

beforeEach(() => {
  storeTestSession()
  listEntries.mockResolvedValue({ entries: sampleEntries() })
  listTags.mockResolvedValue({ tags: KNOWN_TAGS })
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('the review page (FR-R1, FR-R2)', () => {
  it('test_fr_r1_page_is_titled_review_and_review_is_current', async () => {
    await renderReview()

    expect(screen.getByRole('heading', { level: 1, name: 'Review' })).toBeTruthy()
    expect(screen.queryByText('This page is coming soon.')).toBeNull()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Review' }).getAttribute('aria-current')).toBe('page')
  })

  it.each(['phone', 'laptop'] as const)('test_fr_r1_no_primary_button_on_the_%s', async (width) => {
    setViewport(width)
    await renderReview('/review?category=Feedback')
    expect(primaryButtons()).toEqual([])

    if (width === 'phone') {
      await click(filtersToggle())
    }
    listEntries.mockResolvedValue({ entries: [] })
    await click(chip('Learning'))
    expect(screen.getByText(NO_MATCH_TEXT)).toBeTruthy()
    expect(primaryButtons()).toEqual([])

    await click(clearButtons()[0])
    expect(screen.getByText(NO_ENTRIES_TEXT)).toBeTruthy()
    expect(primaryButtons()).toEqual([])
  })
})

describe('the filters send the right query (FR-R1)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_r1_no_filter_loads_once_with_an_empty_query', async () => {
    await renderReview()

    expect(listEntries).toHaveBeenCalledTimes(1)
    expect(lastQuery()).toEqual({})
  })

  it('test_fr_r1_start_date_sends_start_date_only', async () => {
    await renderReview()

    await setDate(startDate(), '2026-01-01')

    expect(listEntries).toHaveBeenCalledTimes(2)
    expect(lastQuery()).toEqual({ start_date: '2026-01-01' })
  })

  it('test_fr_r1_end_date_sends_end_date_only_and_any_date_is_accepted', async () => {
    await renderReview()

    await setDate(endDate(), '2099-12-31')

    expect(lastQuery()).toEqual({ end_date: '2099-12-31' })
    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
  })

  it('test_fr_r1_start_and_end_can_be_the_same_day', async () => {
    await renderReview()

    await setDate(startDate(), '2026-11-05')
    await setDate(endDate(), '2026-11-05')

    expect(lastQuery()).toEqual({ start_date: '2026-11-05', end_date: '2026-11-05' })
    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
  })

  // Chrome edits a date input in segments and reports a value after each year digit
  // (0002-11-01, 0020-11-01, ...). If the page writes any other value into the input while
  // the URL catches up, Chrome drops the typed segments and the date never arrives (#31,
  // QA). jsdom has no segmented editing, so the test watches every value the page writes
  // into the input: there must be none, only the user's own changes.
  it.each([
    ['Start date', 'start_date', '/review', ['0002-11-01', '0020-11-01', '0201-11-01', '2026-11-01'], '2026-11-01'],
    ['End date', 'end_date', '/review', ['0002-11-01', '0020-11-01', '0201-11-01', '2026-11-01'], '2026-11-01'],
    ['Start date', 'start_date', '/review?start_date=2026-11-01', ['0002-11-01', '0020-11-01', '0202-11-01', '2025-11-01'], '2025-11-01'],
    ['End date', 'end_date', '/review?end_date=2026-11-01', ['0002-11-01', '0020-11-01', '0202-11-01', '2025-11-01'], '2025-11-01'],
  ] as const)(
    'test_fr_r1_a_date_typed_key_by_key_into_%s_at_%s_reaches_the_filter_from_%s',
    async (label, param, path, typed, expected) => {
      const valueSetter = vi.spyOn(HTMLInputElement.prototype, 'value', 'set')
      try {
        const { router } = await renderReview(path)
        const input = screen.getByLabelText(label) as HTMLInputElement
        const typedValues: string[] = []

        for (const value of typed) {
          // Record only what reaches the input after the user's own change.
          valueSetter.mockClear()
          await act_(() => fireEvent.change(input, { target: { value } }))
          typedValues.push(input.value)
          const pageWrites = valueSetter.mock.calls.filter((_, index) => valueSetter.mock.contexts[index] === input)
          expect(pageWrites.map(([written]) => written)).toEqual([value])
        }

        expect(typedValues).toEqual(typed)
        expect(new URLSearchParams(router.state.location.search).get(param)).toBe(expected)
        expect(lastQuery()).toEqual({ [param]: expected })
      } finally {
        valueSetter.mockRestore()
      }
    },
  )

  it('test_fr_r1_a_typed_date_follows_clear_filters_and_history', async () => {
    const { router } = await renderWithHistory(['/review?start_date=2026-01-01', '/review?start_date=2026-05-01'])
    await setDate(startDate(), '2026-02-01')
    await setDate(endDate(), '2026-03-01')

    await click(clearButtons()[0])
    expect(startDate().value).toBe('')
    expect(endDate().value).toBe('')

    await setDate(startDate(), '2026-04-01')
    await act(async () => {
      await router.navigate(-1)
    })
    expect(startDate().value).toBe('2026-01-01')
    expect(lastQuery()).toEqual({ start_date: '2026-01-01' })
    await act(async () => {
      await router.navigate(1)
    })
    expect(startDate().value).toBe('2026-04-01')
    await act(async () => {
      await router.navigate('/review')
    })
    expect(startDate().value).toBe('')
    expect(lastQuery()).toEqual({})
  })

  it('test_fr_r1_dates_are_native_date_inputs_and_optional', async () => {
    await renderReview()

    expect(startDate().type).toBe('date')
    expect(endDate().type).toBe('date')
    expect(startDate().required).toBe(false)
    expect(endDate().required).toBe(false)
  })

  it('test_fr_r1_category_chips_in_order_each_toggles_on_its_own', async () => {
    await renderReview()

    const chips = within(categoriesGroup()).getAllByRole('button')
    expect(chips.map((button) => button.textContent)).toEqual(['Achievement', 'Learning', 'Feedback', 'Side project'])
    expect(pressedChips()).toEqual([])

    await click(chip('Feedback'))
    expect(lastQuery()).toEqual({ category: ['Feedback'] })
    await click(chip('Achievement'))
    expect(lastQuery()).toEqual({ category: ['Achievement', 'Feedback'] })
    expect(pressedChips()).toEqual(['Achievement', 'Feedback'])
    // The filter variant: a check icon on each selected chip only.
    expect(chip('Achievement').querySelector('.chip__check')).not.toBeNull()
    expect(chip('Learning').querySelector('.chip__check')).toBeNull()

    await click(chip('Feedback'))
    expect(lastQuery()).toEqual({ category: ['Achievement'] })
    await click(chip('Achievement'))
    expect(lastQuery()).toEqual({})
    expect(listEntries).toHaveBeenCalledTimes(5)
  })

  it('test_fr_r1_tag_sends_one_tag_per_selected_tag', async () => {
    await renderReview()

    await typeTag('py')
    await click(screen.getByRole('option', { name: 'python' }))
    expect(lastQuery()).toEqual({ tag: ['python'] })

    await typeTag('back')
    await click(screen.getByRole('option', { name: 'backend' }))
    expect(lastQuery()).toEqual({ tag: ['python', 'backend'] })
  })

  it('test_fr_r1_combined_filters_are_sent_together', async () => {
    await renderReview()

    await setDate(startDate(), '2026-01-01')
    await setDate(endDate(), '2026-06-30')
    await click(chip('Achievement'))
    await click(chip('Learning'))
    await typeTag('python')
    await click(screen.getByRole('option', { name: 'python' }))

    expect(lastQuery()).toEqual({
      start_date: '2026-01-01',
      end_date: '2026-06-30',
      category: ['Achievement', 'Learning'],
      tag: ['python'],
    })
    expect(listEntries).toHaveBeenCalledTimes(6)
  })

  it('test_fr_r1_filter_not_in_use_is_left_out_of_the_query', async () => {
    await renderReview('/review?start_date=2026-01-01&category=Learning&tag=python')

    expect(lastQuery()).toEqual({ start_date: '2026-01-01', category: ['Learning'], tag: ['python'] })
    await setDate(startDate(), '')
    expect(lastQuery()).toEqual({ category: ['Learning'], tag: ['python'] })
    await click(chip('Learning'))
    expect(lastQuery()).toEqual({ tag: ['python'] })
    await click(screen.getByRole('button', { name: 'Remove python' }))
    expect(lastQuery()).toEqual({})
    for (const [query] of listEntries.mock.calls) {
      for (const value of Object.values(query ?? {})) {
        expect(value).not.toBeUndefined()
        expect(value).not.toEqual([])
      }
    }
  })

  it('test_fr_r1_no_empty_tag_value_is_ever_sent', async () => {
    await renderReview('/review?tag=&tag=%20%20&tag=%20go%20')
    await typeTag('   ')
    await key('Enter')
    await typeTag('zzz')
    await key('Enter')

    expect(lastQuery()).toEqual({ tag: ['go'] })
    await click(screen.getByRole('button', { name: 'Remove go' }))
    expect(lastQuery()).toEqual({})
    for (const [query] of listEntries.mock.calls) {
      for (const tag of query?.tag ?? []) {
        expect(tag.trim()).not.toBe('')
      }
    }
  })

  it('test_fr_r1_typing_in_the_tag_search_sends_no_request', async () => {
    await renderReview()

    await typeTag('p')
    await typeTag('py')
    await typeTag('pyt')
    await typeTag('')

    expect(listEntries).toHaveBeenCalledTimes(1)
  })

  it('test_fr_r1_an_incomplete_date_counts_as_no_date', async () => {
    await renderReview('/review?start_date=2026-01-01')

    // A browser reports an incomplete date as no value.
    await setDate(startDate(), '')

    expect(lastQuery()).toEqual({})
    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(clearButtons()).toEqual([])
  })

  it('test_fr_r1_an_incomplete_start_date_with_an_end_date_shows_no_error', async () => {
    await renderReview('/review?end_date=2026-01-01')
    const calls = listEntries.mock.calls.length

    await setDate(startDate(), '')

    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(startDate().getAttribute('aria-invalid')).toBe('false')
    // Nothing changed, so nothing is sent again.
    expect(listEntries).toHaveBeenCalledTimes(calls)
  })
})

describe('start date after end date (FR-R1)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_r1_start_after_end_shows_the_error_and_sends_no_request', async () => {
    await renderReview()
    await setDate(endDate(), '2026-06-01')
    const calls = listEntries.mock.calls.length
    expect(rows().length).toBeGreaterThan(0)

    await setDate(startDate(), '2026-06-02')

    expect(listEntries).toHaveBeenCalledTimes(calls)
    const message = screen.getByText(DATE_ORDER_ERROR)
    expect(message.classList.contains('field__message')).toBe(true)
    const region = message.parentElement as HTMLElement
    expect(region.getAttribute('role')).toBe('alert')
    for (const input of [startDate(), endDate()]) {
      expect(input.getAttribute('aria-invalid')).toBe('true')
      expect(input.getAttribute('aria-describedby')).toBe(region.id)
    }
    // The results area shows no entries, no total, no state.
    expect(rows()).toEqual([])
    expect(total().textContent).toBe('')
    expect(screen.queryByText('Loading entries…')).toBeNull()
    expect(screen.queryByText(NO_MATCH_TEXT)).toBeNull()
  })

  it('test_fr_r1_fixing_the_dates_clears_the_error_and_loads', async () => {
    await renderReview('/review?start_date=2026-06-02&end_date=2026-06-01')
    expect(listEntries).not.toHaveBeenCalled()
    expect(screen.getByText(DATE_ORDER_ERROR)).toBeTruthy()

    await setDate(startDate(), '2026-05-01')

    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(startDate().getAttribute('aria-invalid')).toBe('false')
    expect(startDate().getAttribute('aria-describedby')).toBeNull()
    expect(listEntries).toHaveBeenCalledTimes(1)
    expect(lastQuery()).toEqual({ start_date: '2026-05-01', end_date: '2026-06-01' })
    expect(rows()).toHaveLength(6)
  })

  it('test_fr_r1_emptying_a_date_clears_the_error', async () => {
    await renderReview('/review?start_date=2026-06-02&end_date=2026-06-01')

    await setDate(endDate(), '')

    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(lastQuery()).toEqual({ start_date: '2026-06-02' })
  })

  it('test_fr_r1_the_error_region_stays_in_the_page_while_empty', async () => {
    await renderReview()

    const id = startDate().closest('.review-page__group')?.querySelector('[role="alert"]')?.id
    expect(id).toBeTruthy()
    expect(document.getElementById(id as string)?.textContent).toBe('')
  })
})

describe('only the newest response is shown (FR-R1)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_r1_an_outdated_response_arriving_later_changes_nothing', async () => {
    await renderReview()
    const older = deferred<EntryList>()
    const newer = deferred<EntryList>()
    listEntries.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)

    await click(chip('Achievement'))
    await click(chip('Learning'))
    await act(async () => {
      newer.resolve({ entries: [makeEntry('learning', '2026-11-01', { category: 'Learning', text: 'Newest answer' })] })
    })
    expect(rowTexts()).toEqual(['Newest answer'])

    await act(async () => {
      older.resolve({ entries: [makeEntry('old', '2026-11-01', { text: 'Outdated answer' })] })
    })
    expect(rowTexts()).toEqual(['Newest answer'])
    expect(total().textContent).toBe('1 entry')
    expect(screen.queryByText('Loading entries…')).toBeNull()
  })

  it('test_fr_r1_an_outdated_failure_changes_nothing', async () => {
    await renderReview()
    const older = deferred<EntryList>()
    listEntries.mockReturnValueOnce(older.promise).mockResolvedValueOnce({ entries: [makeEntry('n', '2026-11-01')] })

    await click(chip('Achievement'))
    await click(chip('Learning'))
    await act(async () => {
      older.reject(new api.NetworkError())
    })

    expect(screen.queryByText(NETWORK_MESSAGE)).toBeNull()
    expect(rowTexts()).toEqual(['Entry n'])
  })
})

describe('the filters in the URL (FR-R1)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_r1_opening_a_url_sets_the_filters_and_loads_the_matching_entries', async () => {
    await renderReview('/review?start_date=2026-01-01&end_date=2026-06-30&category=Achievement&category=Learning&tag=python')

    expect(startDate().value).toBe('2026-01-01')
    expect(endDate().value).toBe('2026-06-30')
    expect(pressedChips()).toEqual(['Achievement', 'Learning'])
    expect(selectedTags()).toEqual(['python'])
    expect(listEntries).toHaveBeenCalledTimes(1)
    expect(lastQuery()).toEqual({
      start_date: '2026-01-01',
      end_date: '2026-06-30',
      category: ['Achievement', 'Learning'],
      tag: ['python'],
    })
  })

  it('test_fr_r1_filter_changes_are_written_to_the_url_with_the_api_names', async () => {
    const { router } = await renderReview()

    await click(chip('Learning'))
    expect(router.state.location.search).toBe('?category=Learning')
    await click(chip('Achievement'))
    await setDate(startDate(), '2026-01-01')
    await setDate(endDate(), '2026-06-30')
    await typeTag('pyth')
    await click(screen.getByRole('option', { name: 'python' }))

    expect(router.state.location.pathname).toBe('/review')
    expect(router.state.location.search).toBe(
      '?start_date=2026-01-01&end_date=2026-06-30&category=Achievement&category=Learning&tag=python',
    )
  })

  it('test_fr_r1_no_filter_in_use_leaves_review_with_no_query', async () => {
    const { router } = await renderReview('/review?category=Learning')

    await click(chip('Learning'))

    expect(router.state.location.pathname).toBe('/review')
    expect(router.state.location.search).toBe('')
  })

  it('test_fr_r1_reloading_keeps_the_filters', async () => {
    const first = await renderReview()
    await click(chip('Feedback'))
    await setDate(startDate(), '2026-02-01')
    const { pathname, search } = first.router.state.location
    first.unmount()
    listEntries.mockClear()

    await renderReview(`${pathname}${search}`)

    expect(pressedChips()).toEqual(['Feedback'])
    expect(startDate().value).toBe('2026-02-01')
    expect(lastQuery()).toEqual({ start_date: '2026-02-01', category: ['Feedback'] })
  })

  it('test_fr_r1_filter_changes_replace_the_history_entry', async () => {
    const { router } = await renderWithHistory(['/', '/review'])

    await click(chip('Learning'))
    await click(chip('Feedback'))
    expect(router.state.historyAction).toBe('REPLACE')

    // Back leaves the review page in one step.
    await act(async () => {
      await router.navigate(-1)
    })
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()

    // Forward comes back with the same filters.
    await act(async () => {
      await router.navigate(1)
    })
    expect(router.state.location.search).toBe('?category=Learning&category=Feedback')
    expect(pressedChips()).toEqual(['Learning', 'Feedback'])
    expect(lastQuery()).toEqual({ category: ['Learning', 'Feedback'] })
  })

  it('test_fr_r1_back_to_the_review_page_shows_the_same_filters', async () => {
    const { router } = await renderWithHistory(['/review'])
    await click(chip('Achievement'))
    await act(async () => {
      await router.navigate('/')
    })

    await act(async () => {
      await router.navigate(-1)
    })

    expect(router.state.location.search).toBe('?category=Achievement')
    expect(pressedChips()).toEqual(['Achievement'])
  })

  it('test_fr_r1_review_link_in_the_navigation_opens_review_without_filters', async () => {
    const { router } = await renderReview('/review?category=Learning&tag=python')
    const nav = screen.getByRole('navigation', { name: 'Main' })

    await click(within(nav).getByRole('link', { name: 'Review' }))

    expect(router.state.location.pathname).toBe('/review')
    expect(router.state.location.search).toBe('')
    expect(pressedChips()).toEqual([])
    expect(selectedTags()).toEqual([])
    expect(lastQuery()).toEqual({})
  })

  it('test_fr_r1_url_values_the_page_cannot_use_are_ignored', async () => {
    await renderReview('/review?start_date=2026-02-30&end_date=abc&category=Wins&category=learning&tag=&tag=%20%20')

    expect(startDate().value).toBe('')
    expect(endDate().value).toBe('')
    expect(pressedChips()).toEqual([])
    expect(selectedTags()).toEqual([])
    expect(clearButtons()).toEqual([])
    expect(lastQuery()).toEqual({})
  })

  it('test_fr_r1_url_tags_are_trimmed_and_a_repeated_tag_is_used_once', async () => {
    await renderReview('/review?tag=%20Python%20&tag=python&tag=PYTHON')

    expect(selectedTags()).toEqual(['Python'])
    expect(lastQuery()).toEqual({ tag: ['Python'] })
  })

  it('test_fr_r1_url_tag_not_in_the_tag_list_is_selected_sent_and_removable', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    const { router } = await renderReview('/review?tag=unknown')

    expect(selectedTags()).toEqual(['unknown'])
    expect(lastQuery()).toEqual({ tag: ['unknown'] })
    expect(screen.getByText(NO_MATCH_TEXT)).toBeTruthy()

    await click(screen.getByRole('button', { name: 'Remove unknown' }))
    expect(selectedTags()).toEqual([])
    expect(router.state.location.search).toBe('')
  })
})

describe('the tag filter (FR-R1)', () => {
  beforeEach(() => {
    setViewport('laptop')
  })

  it('test_fr_r1_offers_tags_that_contain_the_typed_text_ignoring_case', async () => {
    await renderReview()

    expect(listTags).toHaveBeenCalledTimes(1)
    expect(offered()).toEqual([])
    await typeTag('PY')
    expect(offered()).toEqual(['python', 'pytest'])
    expect(tagInput().getAttribute('aria-expanded')).toBe('true')
    await typeTag('e')
    expect(offered()).toEqual(['backend', 'Leadership', 'pytest'])
    await typeTag('nothing')
    expect(offered()).toEqual([])
    expect(tagInput().getAttribute('aria-expanded')).toBe('false')
  })

  it('test_fr_r1_choosing_an_offered_tag_selects_it_and_it_is_no_longer_offered', async () => {
    await renderReview()

    tagInput().focus()
    await typeTag('py')
    await click(screen.getByRole('option', { name: 'python' }))

    expect(selectedTags()).toEqual(['python'])
    expect(tagInput().value).toBe('')
    expect(document.activeElement).toBe(tagInput())
    await typeTag('py')
    expect(offered()).toEqual(['pytest'])
  })

  it('test_fr_r1_arrow_keys_and_enter_choose_a_tag', async () => {
    await renderReview()

    await typeTag('p')
    expect(offered()).toEqual(['Leadership', 'python', 'pytest'])
    await key('ArrowDown')
    await key('ArrowDown')
    expect(tagInput().getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'python' }).id)
    await key('ArrowUp')
    await key('ArrowUp')
    expect(screen.getByRole('option', { selected: true }).textContent).toBe('pytest')
    await key('Enter')

    expect(selectedTags()).toEqual(['pytest'])
    expect(lastQuery()).toEqual({ tag: ['pytest'] })
  })

  it('test_fr_r1_typed_text_that_matches_no_tag_selects_nothing', async () => {
    await renderReview()

    await typeTag('golang')
    await key('Enter')
    await typeTag('golang,')
    await key('Enter')
    // Enter without a highlighted option does nothing either.
    await typeTag('python')
    await key('Enter')

    expect(selectedTags()).toEqual([])
    expect(listEntries).toHaveBeenCalledTimes(1)
  })

  it('test_fr_r1_escape_closes_the_offered_list', async () => {
    await renderReview()

    await typeTag('py')
    await key('Escape')

    expect(offered()).toEqual([])
    expect(tagInput().value).toBe('py')
  })

  it('test_fr_r1_removing_a_tag_returns_focus_to_the_search_field', async () => {
    await renderReview('/review?tag=python&tag=backend')

    await click(screen.getByRole('button', { name: 'Remove python' }))

    expect(selectedTags()).toEqual(['backend'])
    expect(lastQuery()).toEqual({ tag: ['backend'] })
    expect(document.activeElement).toBe(tagInput())
  })

  it('test_fr_r1_hint_sits_under_the_tag_field_and_describes_it', async () => {
    await renderReview()

    const hint = screen.getByText(TAG_FILTER_HINT)
    expect(TAG_FILTER_HINT).toBe('Shows entries with any of the selected tags')
    expect(tagInput().getAttribute('aria-describedby')).toBe(hint.id)
    expect(tagInput().compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // The entry form's hint is not used.
    expect(screen.queryByText(/Press Enter or type a comma/)).toBeNull()
  })

  it('test_fr_r1_user_without_tags_sees_no_tags_yet', async () => {
    listTags.mockResolvedValue({ tags: [] })
    await renderReview('/review?tag=python')

    expect(screen.getByText(NO_TAGS_TEXT)).toBeTruthy()
    expect(NO_TAGS_TEXT).toBe('No tags yet.')
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.queryByText(TAG_FILTER_HINT)).toBeNull()
    // A tag from the URL still shows and filters.
    expect(selectedTags()).toEqual(['python'])
    expect(lastQuery()).toEqual({ tag: ['python'] })
  })

  it('test_fr_r1_failed_tag_list_shows_the_error_and_the_rest_keeps_working', async () => {
    listTags.mockRejectedValue(new api.NetworkError())
    await renderReview('/review?tag=python&tag=go')

    const message = screen.getByText(TAGS_FAILED_TEXT)
    expect(TAGS_FAILED_TEXT).toBe("Tags couldn't be loaded. Reload the page to try again.")
    expect(message.closest('[role="alert"]')).not.toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(selectedTags()).toEqual(['python', 'go'])
    expect(lastQuery()).toEqual({ tag: ['python', 'go'] })

    await click(chip('Learning'))
    expect(lastQuery()).toEqual({ category: ['Learning'], tag: ['python', 'go'] })
    await setDate(startDate(), '2026-01-01')
    expect(lastQuery()).toEqual({ start_date: '2026-01-01', category: ['Learning'], tag: ['python', 'go'] })

    // Removing a tag without a search field moves focus to the next tag, then elsewhere.
    await click(screen.getByRole('button', { name: 'Remove python' }))
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Remove go' }))
    await click(screen.getByRole('button', { name: 'Remove go' }))
    expect(selectedTags()).toEqual([])
    expect(document.activeElement).toBe(chip('Achievement'))
    expect(lastQuery()).toEqual({ start_date: '2026-01-01', category: ['Learning'] })
  })

  it('test_fr_r1_tag_field_offers_nothing_while_the_tag_list_loads', async () => {
    listTags.mockReturnValue(new Promise(() => {}))
    await renderReview()

    await typeTag('py')

    expect(offered()).toEqual([])
    expect(screen.getByText(TAG_FILTER_HINT)).toBeTruthy()
  })
})

describe('"Clear filters" (FR-R1)', () => {
  it('test_fr_r1_clear_filters_shows_only_while_a_filter_is_in_use', async () => {
    setViewport('laptop')
    await renderReview()
    expect(clearButtons()).toEqual([])

    await click(chip('Learning'))
    expect(clearButtons()).toHaveLength(1)
    expect(clearButtons()[0].classList.contains('button--secondary')).toBe(true)

    await click(chip('Learning'))
    expect(clearButtons()).toEqual([])
  })

  it('test_fr_r1_clear_filters_in_the_filter_area_empties_everything_and_keeps_focus', async () => {
    setViewport('laptop')
    const { router } = await renderReview(
      '/review?start_date=2026-06-02&end_date=2026-06-01&category=Feedback&tag=python&tag=unknown',
    )
    expect(screen.getByText(DATE_ORDER_ERROR)).toBeTruthy()

    const clear = clearButtons()[0]
    clear.focus()
    await click(clear)

    expect(startDate().value).toBe('')
    expect(endDate().value).toBe('')
    expect(pressedChips()).toEqual([])
    expect(selectedTags()).toEqual([])
    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(router.state.location.search).toBe('')
    expect(lastQuery()).toEqual({})
    expect(rows()).toHaveLength(6)
    expect(clearButtons()).toEqual([])
    // Focus moves to the first category chip, not to the page.
    expect(document.activeElement).toBe(chip('Achievement'))
  })

  it('test_fr_r1_clear_filters_in_the_no_match_state', async () => {
    setViewport('laptop')
    listEntries.mockResolvedValueOnce({ entries: [] })
    await renderReview('/review?category=Side%20project')

    const emptyState = document.querySelector('.empty-state') as HTMLElement
    expect(within(emptyState).getByText(NO_MATCH_TEXT)).toBeTruthy()
    // The filter area has its own "Clear filters" too.
    expect(clearButtons()).toHaveLength(2)
    const button = within(emptyState).getByRole('button', { name: 'Clear filters' })
    expect(button.classList.contains('button--secondary')).toBe(true)

    await click(button)

    expect(lastQuery()).toEqual({})
    expect(pressedChips()).toEqual([])
    expect(rows()).toHaveLength(6)
    expect(document.activeElement).toBe(chip('Achievement'))
  })

  it('test_fr_r1_clear_filters_on_the_phone_with_the_panel_closed_focuses_the_toggle', async () => {
    listEntries.mockResolvedValueOnce({ entries: [] })
    await renderReview('/review?category=Feedback')
    expect(filtersToggle().getAttribute('aria-expanded')).toBe('false')

    const emptyState = document.querySelector('.empty-state') as HTMLElement
    await click(within(emptyState).getByRole('button', { name: 'Clear filters' }))

    expect(lastQuery()).toEqual({})
    expect(document.activeElement).toBe(filtersToggle())
    // Clearing does not open or close the panel.
    expect(filtersToggle().getAttribute('aria-expanded')).toBe('false')
  })

  it('test_fr_r1_clear_filters_in_the_open_phone_panel_focuses_the_first_chip', async () => {
    await renderReview('/review?category=Feedback')
    await click(filtersToggle())

    await click(clearButtons()[0])

    expect(document.activeElement).toBe(chip('Achievement'))
    expect(filtersToggle().getAttribute('aria-expanded')).toBe('true')
  })
})

describe('the results (FR-R2)', () => {
  it('test_fr_r2_results_grouped_by_category_then_month', async () => {
    await renderReview()

    // Fixed order, each with its count; no heading for a category without entries.
    expect(categoryHeadings()).toEqual(['Achievement 4 entries', 'Learning 1 entry', 'Feedback 1 entry'])
    expect(screen.queryByRole('heading', { name: /Side project/ })).toBeNull()

    const achievement = categorySection('Achievement')
    expect(monthHeadings(achievement)).toEqual(['November 2026', 'October 2026', 'November 2025'])
    const november = within(achievement).getByRole('region', { name: 'November 2026' })
    expect(rowTexts(november)).toEqual(['Created later', 'Created earlier'])
    expect(november.querySelectorAll(':scope > ul > li > .entry-row')).toHaveLength(2)
    expect(monthHeadings(categorySection('Learning'))).toEqual(['October 2026'])
    expect(monthHeadings(categorySection('Feedback'))).toEqual(['November 2026'])
  })

  it('test_fr_r2_rows_keep_the_api_order_within_a_month', async () => {
    // Not in an order the page could make by sorting: it must keep it.
    listEntries.mockResolvedValue({
      entries: [
        makeEntry('a', '2026-11-10', { text: 'First from the API', created_at: '2026-11-10T01:00:00Z' }),
        makeEntry('b', '2026-11-10', { text: 'Second from the API', created_at: '2026-11-10T23:00:00Z' }),
        makeEntry('c', '2026-11-02', { text: 'Third from the API' }),
      ],
    })
    await renderReview()

    expect(rowTexts()).toEqual(['First from the API', 'Second from the API', 'Third from the API'])
  })

  it('test_fr_r2_headings_are_h2_for_categories_and_h3_for_months', async () => {
    await renderReview()

    const heading = within(results()).getByRole('heading', { level: 2, name: /^Achievement/ })
    expect(heading.querySelector('.review-page__dot')?.getAttribute('aria-hidden')).toBe('true')
    expect(heading.querySelector('.review-page__category-count')?.textContent).toBe('4 entries')
    expect(within(results()).getAllByRole('heading', { level: 3 })).toHaveLength(5)
  })

  it('test_fr_r2_total_line_counts_the_matching_entries', async () => {
    await renderReview()

    expect(total().textContent).toBe('6 entries')
    expect(total().getAttribute('role')).toBe('status')

    setViewport('laptop')
    listEntries.mockResolvedValue({ entries: [makeEntry('one', '2026-11-01', { category: 'Learning' })] })
    await click(chip('Learning'))
    expect(total().textContent).toBe('1 entry')
    expect(categoryHeadings()).toEqual(['Learning 1 entry'])
  })

  it('test_fr_r2_rows_are_read_only_with_date_label_text_result_and_tags', async () => {
    await renderReview()

    const learning = categorySection('Learning')
    const [row] = rows(learning)
    const date = within(row).getByText('20 Oct')
    expect(date.tagName).toBe('TIME')
    expect(date.getAttribute('datetime')).toBe('2026-10-20')
    expect(within(row).getByText('Learning').classList.contains('category-label')).toBe(true)
    expect(row.querySelector('.entry-row__text')?.textContent).toBe('Learned pytest fixtures.\nWrote a guide.')
    expect(row.querySelector('.entry-row__result')?.textContent).toBe('Result: The team uses it.')
    const tags = within(row).getByRole('list', { name: 'Tags' })
    expect(within(tags).getAllByRole('listitem').map((tag) => tag.textContent)).toEqual(['python', 'pytest'])
    // No Edit or Delete on any row.
    for (const each of rows()) {
      expect(within(each).queryAllByRole('link')).toEqual([])
      expect(within(each).queryAllByRole('button')).toEqual([])
    }
    expect(screen.queryByRole('link', { name: /^Edit entry/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Delete entry/ })).toBeNull()
  })

  it('test_fr_r2_dates_do_not_shift_in_a_time_zone_behind_utc', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    expect(new Date('2026-11-01').getDate()).toBe(31)
    listEntries.mockResolvedValue({
      entries: [makeEntry('nov1', '2026-11-01'), makeEntry('oct1', '2026-10-01', { category: 'Learning' })],
    })

    await renderReview()

    expect(within(categorySection('Achievement')).getByText('1 Nov')).toBeTruthy()
    expect(monthHeadings(categorySection('Achievement'))).toEqual(['November 2026'])
    expect(within(categorySection('Learning')).getByText('1 Oct')).toBeTruthy()
    expect(monthHeadings(categorySection('Learning'))).toEqual(['October 2026'])
    expect(screen.queryByText('September 2026')).toBeNull()
  })

  it('test_fr_r2_no_match_state_with_clear_filters_and_the_review_illustration', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview('/review?category=Feedback')

    expect(total().textContent).toBe('0 entries')
    const emptyState = document.querySelector('.empty-state') as HTMLElement
    expect(within(emptyState).getByText('No entries match these filters.')).toBeTruthy()
    // #77: the review drawing in the empty state's illustration slot.
    expect(emptyState.querySelector('.empty-state__illustration .illustration--review')).not.toBeNull()
    expect(within(emptyState).getByRole('button', { name: 'Clear filters' })).toBeTruthy()
    expect(categoryHeadings()).toEqual([])
  })

  it('test_fr_r2_no_entries_state_with_a_secondary_new_entry_link', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    const { router } = await renderReview()

    expect(total().textContent).toBe('0 entries')
    const emptyState = document.querySelector('.empty-state') as HTMLElement
    expect(within(emptyState).getByText('No entries yet. Write your first win.')).toBeTruthy()
    expect(within(emptyState).queryByRole('button')).toBeNull()
    const link = within(emptyState).getByRole('link', { name: 'New entry' })
    expect(link.getAttribute('href')).toBe('/entries/new')
    expect(link.classList.contains('button--secondary')).toBe(true)
    expect(link.classList.contains('button--primary')).toBe(false)

    await click(link)
    expect(router.state.location.pathname).toBe('/entries/new')
  })
})

describe('loading and errors (FR-R2, §12)', () => {
  it('test_fr_r2_first_load_shows_only_the_loading_line_then_the_waking_up_hint', async () => {
    vi.useFakeTimers()
    listEntries.mockReturnValue(new Promise(() => {}))
    await renderReview()

    const status = screen.getByText('Loading entries…')
    expect(status.getAttribute('role')).toBe('status')
    expect(status.querySelector('.spinner')).not.toBeNull()
    expect(total().textContent).toBe('')
    expect(categoryHeadings()).toEqual([])
    expect(document.querySelector('.empty-state')).toBeNull()
    expect(screen.queryByText(WAKING_UP)).toBeNull()

    act(() => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).getAttribute('role')).toBe('status')
  })

  it('test_fr_r2_previous_results_stay_while_new_ones_load', async () => {
    setViewport('laptop')
    await renderReview()
    const next = deferred<EntryList>()
    listEntries.mockReturnValueOnce(next.promise)

    await click(chip('Learning'))

    expect(screen.getByText('Loading entries…')).toBeTruthy()
    expect(rows()).toHaveLength(6)
    expect(total().textContent).toBe('6 entries')
    const groups = document.querySelector('.review-page__groups') as HTMLElement
    expect(groups.getAttribute('aria-busy')).toBe('true')
    // The loading line sits above the total line.
    const loading = screen.getByText('Loading entries…')
    expect(loading.compareDocumentPosition(total()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    await act(async () => {
      next.resolve({ entries: [makeEntry('l', '2026-11-01', { category: 'Learning' })] })
    })
    expect(screen.queryByText('Loading entries…')).toBeNull()
    expect(rows()).toHaveLength(1)
    expect(total().textContent).toBe('1 entry')
    expect(groups.getAttribute('aria-busy')).toBe('false')
  })

  it('test_fr_r2_waking_up_hint_also_shows_on_a_slow_filter_change', async () => {
    setViewport('laptop')
    await renderReview()
    vi.useFakeTimers()
    listEntries.mockReturnValueOnce(new Promise(() => {}))

    await click(chip('Learning'))
    act(() => {
      vi.advanceTimersByTime(10_000)
    })

    expect(screen.getByText(WAKING_UP)).toBeTruthy()
    expect(rows()).toHaveLength(6)
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r2_load_with_%s_shows_the_error_and_try_again', async (_label, error, text) => {
    setViewport('laptop')
    await renderReview('/review?category=Learning')
    listEntries.mockRejectedValueOnce(error)
    await click(chip('Feedback'))

    // The results are replaced by the error.
    expect(screen.getByText(text).closest('[role="alert"]')).not.toBeNull()
    expect(rows()).toEqual([])
    expect(total().textContent).toBe('')
    const retry = screen.getByRole('button', { name: 'Try again' })
    expect(retry.classList.contains('button--secondary')).toBe(true)
    // The filters stay usable.
    expect(chip('Achievement').disabled).toBe(false)

    const load = deferred<EntryList>()
    listEntries.mockReturnValueOnce(load.promise)
    await click(retry)
    expect(lastQuery()).toEqual({ category: ['Learning', 'Feedback'] })
    // Trying again shows the first-load state.
    expect(screen.getByText('Loading entries…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    expect(rows()).toEqual([])

    await act(async () => {
      load.resolve({ entries: sampleEntries() })
    })
    expect(rows()).toHaveLength(6)
  })
})

// Keyboard focus after a failed retry (#84): the new "Try again" gets focus, unless the user
// moved on, for example to a filter. Only a load that "Try again" started moves focus.
describe('keyboard focus after a failed retry (FR-R2, #84)', () => {
  function tryAgain(): HTMLButtonElement {
    return screen.getByRole('button', { name: 'Try again' }) as HTMLButtonElement
  }

  async function pressTryAgain(): Promise<void> {
    tryAgain().focus()
    await click(tryAgain())
  }

  it('test_fr_r2_failed_retry_moves_focus_to_the_new_try_again', async () => {
    setViewport('laptop')
    listEntries.mockRejectedValueOnce(new api.NetworkError())
    await renderReview()
    // The first failure moves no focus.
    expect(document.activeElement).toBe(document.body)
    const first = tryAgain()
    const load = deferred<EntryList>()
    listEntries.mockReturnValueOnce(load.promise)

    await pressTryAgain()
    expect(screen.getByText('Loading entries…')).toBeTruthy()
    await act(async () => {
      load.reject(new api.NetworkError())
    })

    expect(tryAgain()).not.toBe(first)
    expect(document.activeElement).toBe(tryAgain())
  })

  it('test_fr_r2_failed_retry_keeps_focus_on_the_filter_the_user_moved_to', async () => {
    setViewport('laptop')
    listEntries.mockRejectedValueOnce(new api.NetworkError())
    await renderReview()
    const load = deferred<EntryList>()
    listEntries.mockReturnValueOnce(load.promise)

    await pressTryAgain()
    chip('Achievement').focus()
    await act(async () => {
      load.reject(new api.NetworkError())
    })

    expect(tryAgain()).toBeTruthy()
    expect(document.activeElement).toBe(chip('Achievement'))
  })

  it('test_fr_r2_a_failed_filter_change_after_a_successful_retry_moves_no_focus', async () => {
    setViewport('laptop')
    listEntries.mockRejectedValueOnce(new api.NetworkError())
    await renderReview()
    await pressTryAgain()
    // The retry succeeded: focus is not moved.
    expect(rows()).toHaveLength(6)
    expect(document.activeElement).toBe(document.body)

    listEntries.mockRejectedValueOnce(new api.NetworkError())
    await click(chip('Feedback'))

    expect(tryAgain()).toBeTruthy()
    expect(document.activeElement).toBe(document.body)
  })
})

describe('phone and laptop (FR-R1)', () => {
  it('test_fr_r1_phone_filters_sit_in_a_collapsed_panel_with_a_toggle', async () => {
    await renderReview()

    const toggle = filtersToggle()
    expect(toggle.textContent).toBe('Filters')
    expect(toggle.classList.contains('button--secondary')).toBe(true)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    const panel = document.getElementById(toggle.getAttribute('aria-controls') as string) as HTMLElement
    expect(panel.hidden).toBe(true)
    expect(screen.queryByRole('group', { name: 'Categories' })).toBeNull()
    // The toggle sits under the title, the panel after it.
    const title = screen.getByRole('heading', { level: 1, name: 'Review' })
    expect(title.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(toggle.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    await click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(panel.hidden).toBe(false)
    expect(categoriesGroup()).toBeTruthy()

    await click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(panel.hidden).toBe(true)
  })

  it('test_fr_r1_phone_toggle_shows_the_number_of_filters_in_use', async () => {
    await renderReview('/review?start_date=2026-01-01&end_date=2026-06-30&category=Learning&tag=python&tag=go')

    const toggle = screen.getByRole('button', { name: 'Filters 5 in use' })
    expect(toggle.querySelector('.review-page__count')?.textContent).toBe('5 in use')
    // The results already reflect the filters while the panel is closed.
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(lastQuery()).toEqual({
      start_date: '2026-01-01',
      end_date: '2026-06-30',
      category: ['Learning'],
      tag: ['python', 'go'],
    })

    await click(toggle)
    await click(chip('Achievement'))
    expect(screen.getByRole('button', { name: 'Filters 6 in use' })).toBe(toggle)
  })

  it('test_fr_r1_phone_toggle_has_no_count_for_ignored_or_incomplete_values', async () => {
    await renderReview('/review?start_date=2026-02-30&category=Wins&tag=')

    expect(filtersToggle().textContent).toBe('Filters')
    expect(filtersToggle().querySelector('.review-page__count')).toBeNull()
  })

  it('test_fr_r1_phone_panel_is_open_while_the_date_error_shows', async () => {
    await renderReview('/review?start_date=2026-06-02&end_date=2026-06-01')

    const toggle = filtersToggle()
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText(DATE_ORDER_ERROR)).toBeTruthy()
    expect(listEntries).not.toHaveBeenCalled()

    // Pressing "Filters" leaves it open.
    await click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    // Fixing the dates does not close the panel under the user.
    await setDate(startDate(), '2026-05-01')
    expect(screen.queryByText(DATE_ORDER_ERROR)).toBeNull()
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(categoriesGroup()).toBeTruthy()
  })

  it('test_fr_r1_laptop_filters_are_always_shown_without_a_toggle', async () => {
    setViewport('laptop')
    await renderReview('/review?category=Learning')

    expect(screen.queryByRole('button', { name: /^Filters/ })).toBeNull()
    expect(categoriesGroup()).toBeTruthy()
    expect(startDate()).toBeTruthy()
    expect(tagInput()).toBeTruthy()
    const panel = document.querySelector('.review-page__filters') as HTMLElement
    expect(panel.hidden).toBe(false)
  })

  it('test_fr_r1_switching_from_phone_to_laptop_shows_the_filters', async () => {
    await renderReview()
    expect(screen.queryByRole('group', { name: 'Categories' })).toBeNull()

    setViewport('laptop')

    expect(screen.queryByRole('button', { name: /^Filters/ })).toBeNull()
    expect(categoriesGroup()).toBeTruthy()
  })
})

// §9 Design, #77: the review drawing shows in both empty states and nowhere else.
describe('the review illustration (§9 Design)', () => {
  function illustrations(): SVGSVGElement[] {
    return Array.from(document.querySelectorAll<SVGSVGElement>('svg.illustration'))
  }

  /** The one drawing on the page: the review drawing, above the empty state's sentence. */
  function reviewIllustration(text: string): SVGSVGElement {
    const svgs = illustrations()
    expect(svgs).toHaveLength(1)
    const svg = svgs[0]
    expect(svg.classList.contains('illustration--review')).toBe(true)
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('focusable')).toBe('false')
    expect(svg.parentElement?.classList.contains('empty-state__illustration')).toBe(true)
    const sentence = within(svg.closest('.empty-state') as HTMLElement).getByText(text)
    expect(svg.compareDocumentPosition(sentence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Still no filled plum button on the review page (#32).
    expect(document.querySelectorAll('.button--primary')).toHaveLength(0)
    return svg
  }

  it('test_design_review_no_match_state_shows_the_review_illustration', async () => {
    setViewport('laptop')
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview('/review?category=Feedback')

    reviewIllustration(NO_MATCH_TEXT)
    expect(screen.getAllByRole('button', { name: 'Clear filters' }).length).toBeGreaterThan(0)
  })

  it('test_design_review_no_entries_state_shows_the_review_illustration', async () => {
    setViewport('laptop')
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview()

    const svg = reviewIllustration(NO_ENTRIES_TEXT)
    const emptyState = svg.closest('.empty-state') as HTMLElement
    expect(within(emptyState).getByRole('link', { name: 'New entry' }).classList.contains('button--secondary')).toBe(
      true,
    )
  })

  it('test_design_review_no_illustration_with_results', async () => {
    setViewport('laptop')
    await renderReview()

    expect(rows()).toHaveLength(6)
    expect(illustrations()).toEqual([])
  })

  it('test_design_review_no_illustration_on_first_load_or_after_a_failed_load', async () => {
    setViewport('laptop')
    const load = deferred<EntryList>()
    listEntries.mockReturnValueOnce(load.promise)
    await renderReview()
    expect(screen.getByText('Loading entries…')).toBeTruthy()
    expect(illustrations()).toEqual([])

    await act(async () => {
      load.reject(new api.NetworkError())
    })
    expect(screen.getByText(NETWORK_MESSAGE)).toBeTruthy()
    expect(illustrations()).toEqual([])
  })

  it('test_design_review_no_illustration_with_the_date_error', async () => {
    setViewport('laptop')
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview()
    reviewIllustration(NO_ENTRIES_TEXT)

    await setDate(endDate(), '2026-06-01')
    await setDate(startDate(), '2026-06-02')

    expect(screen.getByText(DATE_ORDER_ERROR)).toBeTruthy()
    expect(illustrations()).toEqual([])
  })

  it('test_design_review_illustration_stays_while_new_results_load', async () => {
    setViewport('laptop')
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview('/review?category=Feedback')
    const before = reviewIllustration(NO_MATCH_TEXT)
    const next = deferred<EntryList>()
    listEntries.mockReturnValueOnce(next.promise)

    await click(chip('Learning'))

    expect(screen.getByText('Loading entries…')).toBeTruthy()
    // The same drawing, not unmounted or replaced while the new results load (#31).
    expect(reviewIllustration(NO_MATCH_TEXT)).toBe(before)

    await act(async () => {
      next.resolve({ entries: [makeEntry('l', '2026-11-01', { category: 'Learning' })] })
    })
    expect(rows()).toHaveLength(1)
    expect(illustrations()).toEqual([])
  })
})
