import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import {
  AiUnavailableError,
  LimitReachedError,
  NetworkError,
  NoMatchingEntriesError,
  NotAuthenticatedError,
  NotFoundError,
  UnknownError,
  type Entry,
  type Summary,
  type SummaryFilter,
} from '../api/index.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { routes } from '../routes.tsx'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

// The summary panel on the review page (#32): drafting a summary of exactly the entries
// shown (FR-R3), and editing and saving the draft (FR-R5). The API client is mocked: no
// test ever makes a real AI call.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    listEntries: vi.fn(),
    listTags: vi.fn(),
    generateSummary: vi.fn(),
    updateSummary: vi.fn(),
    createEntry: vi.fn(),
    updateEntry: vi.fn(),
    deleteEntry: vi.fn(),
    logout: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const listEntries = vi.mocked(api.listEntries)
const listTags = vi.mocked(api.listTags)
const generateSummary = vi.mocked(api.generateSummary)
const updateSummary = vi.mocked(api.updateSummary)
const logout = vi.mocked(api.logout)

const PERIOD_PATH = '/review?start_date=2026-01-01&end_date=2026-06-30'
const PERIOD: SummaryFilter = { period_start: '2026-01-01', period_end: '2026-06-30' }
const SUMMARY_ID = '6f1c2a5e-0000-4000-8000-000000000032'
const DRAFT_TEXT = 'Mock summary\n\nLed the incident review.\nShipped the export.'

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const PROGRESS = 'Writing your summary… This can take up to a minute.'
const NEED_DATES = 'Choose a start and end date to draft a summary.'
const DATE_ORDER = 'Choose a start date on or before the end date to draft a summary.'
const NOTHING = "No entries match these filters, so there's nothing to summarise."
const DRAFT_NOTE = 'This draft is saved in Summaries. Edit it as you like, then save your changes.'
const GONE = "This summary no longer exists, so your changes can't be saved."

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

function sampleEntries(count = 3): Entry[] {
  return Array.from({ length: count }, (_, index) =>
    makeEntry(`e${index}`, `2026-0${(index % 6) + 1}-1${index % 9}`, {
      category: index % 2 === 0 ? 'Achievement' : 'Learning',
    }),
  )
}

function makeSummary(filter: SummaryFilter, text = DRAFT_TEXT, id = SUMMARY_ID): Summary {
  return { id, text, filter, created_at: '2026-11-13T09:00:00Z', updated_at: '2026-11-13T09:00:00Z' }
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

async function renderReview(path = PERIOD_PATH) {
  const result = renderRoute(path)
  await flush()
  return result
}

async function renderWithHistory(entries: string[]) {
  const router = createMemoryRouter(routes, { initialEntries: entries, initialIndex: entries.length - 1 })
  connectLoginRedirect(router)
  render(<RouterProvider router={router} />)
  await flush()
  return { router }
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element)
  })
}

async function type(element: HTMLElement, value: string): Promise<void> {
  await act(async () => {
    fireEvent.change(element, { target: { value } })
  })
}

function panel(): HTMLElement {
  return screen.getByRole('region', { name: 'Summary' })
}

function draftButton(): HTMLButtonElement {
  return within(panel()).getByRole('button', { name: /^(Draft summary|Draft again|Drafting…)$/ }) as HTMLButtonElement
}

function saveButton(): HTMLButtonElement {
  return within(panel()).getByRole('button', { name: /^(Save summary|Saving…)$/ }) as HTMLButtonElement
}

function field(): HTMLTextAreaElement {
  return within(panel()).getByLabelText('Summary text') as HTMLTextAreaElement
}

function sourceLine(): HTMLElement {
  return within(panel()).getByText(/^Entries from /)
}

function progress(): HTMLElement {
  return panel().querySelector('.summary-panel__progress') as HTMLElement
}

/** The text the draft button points at with aria-describedby, or null. */
function buttonHint(): string | null {
  const id = draftButton().getAttribute('aria-describedby')
  return id === null ? null : (document.getElementById(id)?.textContent ?? null)
}

function primaryButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('.button--primary'))
}

function chip(name: string): HTMLButtonElement {
  return within(screen.getByRole('group', { name: 'Categories' })).getByRole('button', { name }) as HTMLButtonElement
}

function navLink(name: string): HTMLElement {
  return within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name })
}

function openDialog(): HTMLDialogElement | null {
  return document.querySelector<HTMLDialogElement>('dialog[open]')
}

function infoNotice(): string {
  return panel().querySelector('.message--info')?.textContent ?? ''
}

function errorNotice(): string {
  return panel().querySelector('.message--error')?.textContent ?? ''
}

/** The redirect the API client calls after a "not authenticated" response. */
function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

/** Renders the review page with a period and drafts a summary that arrives at once. */
async function renderWithDraft(summary = makeSummary(PERIOD)) {
  const result = await renderReview()
  generateSummary.mockResolvedValueOnce(summary)
  await click(draftButton())
  return result
}

beforeEach(() => {
  storeTestSession()
  listEntries.mockResolvedValue({ entries: sampleEntries() })
  listTags.mockResolvedValue({ tags: ['python', 'Leadership'] })
  updateSummary.mockImplementation(async (id, body) => makeSummary(PERIOD, body.text, id))
  logout.mockImplementation(async () => removeTestSession())
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
  setViewport('laptop')
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('the panel (FR-R3)', () => {
  it('test_fr_r3_panel_titled_summary_with_the_draft_button_and_its_line', async () => {
    await renderReview()

    expect(within(panel()).getByRole('heading', { level: 2, name: 'Summary' })).toBeTruthy()
    expect(draftButton().textContent).toBe('Draft summary')
    expect(draftButton().disabled).toBe(false)
    expect(draftButton().className).toContain('button--secondary')
    expect(draftButton().querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    expect(buttonHint()).toBe('Draft a summary of the 3 entries shown.')
    // No draft yet: no text field, no Save summary, and no filled plum button on the page.
    expect(within(panel()).queryByLabelText('Summary text')).toBeNull()
    expect(within(panel()).queryByRole('button', { name: 'Save summary' })).toBeNull()
    expect(primaryButtons()).toEqual([])
  })

  it.each(['phone', 'laptop'] as const)('test_fr_r3_panel_sits_after_the_results_on_the_%s', async (width) => {
    setViewport(width)
    await renderReview()

    const results = document.querySelector('.review-page__results') as HTMLElement
    const layout = document.querySelector('.review-page__layout') as HTMLElement
    // Filters and results in one column, the panel next to it (beside on wide windows, below otherwise).
    expect(layout.children[0].contains(results)).toBe(true)
    expect(layout.children[1]).toBe(panel())
  })

  it('test_fr_r3_one_entry_says_1_entry', async () => {
    listEntries.mockResolvedValue({ entries: sampleEntries(1) })
    await renderReview()

    expect(buttonHint()).toBe('Draft a summary of the 1 entry shown.')
  })

  it('test_fr_r3_with_a_draft_save_summary_is_the_one_primary_button', async () => {
    await renderWithDraft()

    expect(primaryButtons()).toEqual([saveButton()])
    expect(draftButton().textContent).toBe('Draft again')
    expect(draftButton().className).toContain('button--secondary')
    expect(draftButton().querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    expect(buttonHint()).toBe('Draft a new summary of the 3 entries shown. This draft stays in Summaries.')
  })
})

describe('when drafting is possible (FR-R3)', () => {
  it('test_fr_r3_draft_uses_the_shown_filter', async () => {
    await renderReview()
    generateSummary.mockResolvedValue(makeSummary(PERIOD))

    await click(draftButton())

    expect(generateSummary).toHaveBeenCalledTimes(1)
    // Exactly the period: no empty categories or tags.
    expect(generateSummary.mock.calls[0][0]).toStrictEqual(PERIOD)
  })

  it('test_fr_r3_draft_uses_the_shown_categories_and_tags', async () => {
    await renderReview(`${PERIOD_PATH}&category=Learning&category=Achievement&tag=python&tag=%20Leadership%20`)
    generateSummary.mockResolvedValue(makeSummary(PERIOD))

    await click(draftButton())

    expect(generateSummary.mock.calls[0][0]).toStrictEqual({
      ...PERIOD,
      categories: ['Achievement', 'Learning'],
      tags: ['python', 'Leadership'],
    })
  })

  it.each([
    ['no dates', '/review'],
    ['only a start date', '/review?start_date=2026-01-01'],
    ['only an end date', '/review?end_date=2026-06-30'],
    ['a date the page cannot use', '/review?start_date=2026-02-30&end_date=2026-06-30'],
  ])('test_fr_r3_disabled_without_a_period_%s', async (_name, path) => {
    await renderReview(path)

    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBe(NEED_DATES)
  })

  it('test_fr_r3_disabled_while_a_typed_date_is_incomplete', async () => {
    await renderReview()
    expect(draftButton().disabled).toBe(false)

    await type(screen.getByLabelText('End date'), '')

    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBe(NEED_DATES)
  })

  it('test_fr_r3_disabled_while_the_start_date_is_after_the_end_date', async () => {
    await renderReview('/review?start_date=2026-07-01&end_date=2026-06-30')

    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBe(DATE_ORDER)
    // The filters' own date error shows as well.
    expect(screen.getByText('Choose a start date on or before the end date.')).toBeTruthy()
  })

  it('test_fr_r3_disabled_when_no_entries_are_shown', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    await renderReview()

    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBe(NOTHING)
  })

  it('test_fr_r3_disabled_without_a_second_message_while_loading_or_after_a_failed_load', async () => {
    const load = deferred<api.EntryList>()
    listEntries.mockReturnValue(load.promise)
    await renderReview()

    expect(screen.getByText('Loading entries…')).toBeTruthy()
    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBeNull()
    expect(panel().querySelector('.summary-panel__line:not(.summary-panel__progress)')).toBeNull()

    await act(async () => {
      load.reject(new NetworkError())
    })
    expect(screen.getByText(NETWORK_MESSAGE)).toBeTruthy()
    expect(within(panel()).queryByText(NETWORK_MESSAGE)).toBeNull()
    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBeNull()
  })

  it('test_fr_r3_disabled_while_new_entries_load_after_a_filter_change', async () => {
    await renderReview()
    const load = deferred<api.EntryList>()
    listEntries.mockReturnValue(load.promise)

    await click(chip('Learning'))

    // The previous results stay on screen, but they are not the entries for this filter.
    expect(draftButton().disabled).toBe(true)
    expect(buttonHint()).toBeNull()
    await act(async () => {
      load.resolve({ entries: sampleEntries(2) })
    })
    expect(draftButton().disabled).toBe(false)
    expect(buttonHint()).toBe('Draft a summary of the 2 entries shown.')
  })
})

describe('drafting (FR-R3)', () => {
  it('test_fr_r3_progress_line_and_a_double_tap_sends_one_request', async () => {
    await renderReview()
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)
    expect(progress().getAttribute('role')).toBe('status')
    expect(progress().textContent).toBe('')

    await act(async () => {
      fireEvent.click(draftButton())
      fireEvent.click(draftButton())
    })
    await click(draftButton())

    expect(generateSummary).toHaveBeenCalledTimes(1)
    expect(draftButton().disabled).toBe(true)
    expect(draftButton().textContent).toBe('Drafting…')
    expect(progress().textContent).toBe(PROGRESS)
    // The progress line replaces the count line.
    expect(within(panel()).queryByText('Draft a summary of the 3 entries shown.')).toBeNull()

    await act(async () => {
      answer.resolve(makeSummary(PERIOD))
    })
    expect(progress().textContent).toBe('')
    expect(generateSummary).toHaveBeenCalledTimes(1)
  })

  it('test_fr_r3_a_filter_change_while_drafting_does_not_change_the_request', async () => {
    await renderReview()
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)
    await click(draftButton())

    // The filters stay usable and the results follow them.
    listEntries.mockClear()
    await click(chip('Learning'))
    expect(chip('Learning').getAttribute('aria-pressed')).toBe('true')
    expect(listEntries).toHaveBeenCalledWith({
      ...{ start_date: '2026-01-01', end_date: '2026-06-30' },
      category: ['Learning'],
    })

    await act(async () => {
      answer.resolve(makeSummary(PERIOD))
    })

    expect(generateSummary).toHaveBeenCalledTimes(1)
    expect(generateSummary.mock.calls[0][0]).toStrictEqual(PERIOD)
    // The draft is the one for the filter at the tap, as its source line says.
    expect(sourceLine().textContent).toBe('Entries from 1 Jan 2026 – 30 Jun 2026 · All categories · All tags')
  })

  it('test_fr_r3_draft_arrives_and_focus_moves_to_the_source_line', async () => {
    await renderReview()
    generateSummary.mockResolvedValue(makeSummary(PERIOD))
    draftButton().focus()

    await click(draftButton())

    expect(document.activeElement).toBe(sourceLine())
    expect(sourceLine().getAttribute('tabindex')).toBe('-1')
    expect(document.activeElement).not.toBe(field())
  })

  it('test_fr_r3_the_panel_is_scrolled_into_view_when_it_is_outside_the_window', async () => {
    setViewport('phone')
    await renderReview()
    generateSummary.mockResolvedValue(makeSummary(PERIOD))
    vi.spyOn(panel(), 'getBoundingClientRect').mockReturnValue({ top: 1500 } as DOMRect)

    await click(draftButton())

    expect(window.scrollTo).toHaveBeenCalledWith({ top: window.scrollY + 1500, behavior: 'smooth' })
  })

  it('test_fr_r3_the_panel_is_not_scrolled_when_its_top_is_in_view', async () => {
    await renderReview()
    generateSummary.mockResolvedValue(makeSummary(PERIOD))
    vi.spyOn(panel(), 'getBoundingClientRect').mockReturnValue({ top: 24 } as DOMRect)

    await click(draftButton())

    expect(window.scrollTo).not.toHaveBeenCalled()
  })

  it('test_fr_r3_leaving_review_while_drafting_changes_nothing_on_the_next_page', async () => {
    const { router } = await renderReview()
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)
    await click(draftButton())

    await click(navLink('Entries'))
    expect(router.state.location.pathname).toBe('/')
    await act(async () => {
      answer.resolve(makeSummary(PERIOD))
    })

    expect(router.state.location.pathname).toBe('/')
    expect(openDialog()).toBeNull()
    expect(screen.queryByRole('region', { name: 'Summary' })).toBeNull()
    expect(window.scrollTo).not.toHaveBeenCalled()
  })

  it('test_fr_r3_leaving_review_before_a_failure_shows_nothing', async () => {
    const { router } = await renderReview()
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)
    await click(draftButton())

    await click(navLink('Entries'))
    await act(async () => {
      answer.reject(new AiUnavailableError('server text', 503))
    })

    expect(router.state.location.pathname).toBe('/')
    expect(screen.queryByText("The summary couldn't be written right now. Please try again later.")).toBeNull()
  })
})

describe('the draft (FR-R3, FR-R5)', () => {
  it('test_fr_r3_draft_shows_the_source_line_note_and_editable_text', async () => {
    await renderWithDraft()

    expect(sourceLine().textContent).toBe('Entries from 1 Jan 2026 – 30 Jun 2026 · All categories · All tags')
    expect(within(panel()).getByText(DRAFT_NOTE)).toBeTruthy()
    expect(field().tagName).toBe('TEXTAREA')
    // Line breaks kept.
    expect(field().value).toBe(DRAFT_TEXT)
    expect(field().readOnly).toBe(false)
    expect(within(panel()).queryByText('Draft summary')).toBeNull()
  })

  it('test_fr_r3_source_line_comes_from_the_saved_filter', async () => {
    await renderReview()
    // The saved filter differs from the filters shown: the line follows the summary.
    await renderWithDraftFrom({
      period_start: '2025-12-31',
      period_end: '2026-01-01',
      categories: ['Learning', 'Achievement'],
      tags: ['python', 'Leadership'],
    })

    expect(sourceLine().textContent).toBe(
      'Entries from 31 Dec 2025 – 1 Jan 2026 · Achievement, Learning · python, Leadership',
    )
  })

  it('test_fr_r5_save_edited_draft', async () => {
    await renderWithDraft()
    const answer = deferred<Summary>()
    updateSummary.mockReturnValue(answer.promise)
    await type(field(), 'My own words.\nSecond line.')
    saveButton().focus()

    await click(saveButton())

    expect(updateSummary).toHaveBeenCalledTimes(1)
    expect(updateSummary).toHaveBeenCalledWith(SUMMARY_ID, { text: 'My own words.\nSecond line.' })
    // While saving: Save summary busy, Draft again disabled, the text read-only.
    expect(saveButton().textContent).toBe('Saving…')
    expect(saveButton().disabled).toBe(true)
    expect(draftButton().disabled).toBe(true)
    expect(field().readOnly).toBe(true)
    await click(saveButton())
    expect(updateSummary).toHaveBeenCalledTimes(1)

    await act(async () => {
      answer.resolve(makeSummary(PERIOD, 'My own words.\nSecond line.'))
    })

    const savedRegion = panel().querySelector('.saved-region') as HTMLElement
    expect(savedRegion.getAttribute('role')).toBe('status')
    expect(within(savedRegion).getByText('Summary saved.')).toBeTruthy()
    expect(field().value).toBe('My own words.\nSecond line.')
    expect(document.activeElement).toBe(saveButton())
    expect(draftButton().disabled).toBe(false)
  })

  it('test_fr_r5_saved_text_counts_as_unchanged', async () => {
    const { router } = await renderWithDraft()
    await type(field(), 'Edited')
    await click(saveButton())

    await click(navLink('Entries'))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/')
  })

  it.each(['', '   \n\t '])('test_fr_r5_empty_text_is_not_sent_%#', async (empty) => {
    await renderWithDraft()
    await type(field(), empty)

    await click(saveButton())

    expect(updateSummary).not.toHaveBeenCalled()
    expect(within(panel()).getByText('Write your summary, then save.')).toBeTruthy()
    expect(field().getAttribute('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(field())

    await type(field(), 'Now with words')
    expect(within(panel()).queryByText('Write your summary, then save.')).toBeNull()
    expect(field().getAttribute('aria-invalid')).toBe('false')
  })

  it.each([
    ['not_found', new NotFoundError('server text', 404), GONE],
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['another error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r5_failed_save_keeps_the_text_after_%s', async (_name, error, message) => {
    await renderWithDraft()
    updateSummary.mockRejectedValue(error)
    await type(field(), 'Edited text')
    saveButton().focus()

    await click(saveButton())

    expect(errorNotice()).toBe(message)
    expect(panel().querySelector('.message--error')?.getAttribute('role')).toBe('alert')
    expect(within(panel()).queryByText('server text')).toBeNull()
    expect(field().value).toBe('Edited text')
    expect(within(panel()).queryByText('Summary saved.')).toBeNull()
    expect(document.activeElement).toBe(saveButton())
    // Still unsaved.
    await click(navLink('Entries'))
    expect(openDialog()).not.toBeNull()
  })

  it('test_fr_r5_editing_and_saving_never_change_an_entry', async () => {
    await renderWithDraft()
    await type(field(), 'Edited text')
    await click(saveButton())

    expect(api.createEntry).not.toHaveBeenCalled()
    expect(api.updateEntry).not.toHaveBeenCalled()
    expect(api.deleteEntry).not.toHaveBeenCalled()
  })
})

/** Drafts a summary whose saved filter is `filter`, on the page already rendered. */
async function renderWithDraftFrom(filter: SummaryFilter) {
  generateSummary.mockResolvedValueOnce(makeSummary(filter))
  await click(draftButton())
}

describe('"Draft again" (FR-R3)', () => {
  it('test_fr_r3_draft_again_without_changes_drafts_the_filter_shown_now', async () => {
    await renderWithDraft()
    await click(chip('Learning'))
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)

    await click(draftButton())

    expect(openDialog()).toBeNull()
    expect(generateSummary).toHaveBeenCalledTimes(2)
    expect(generateSummary.mock.calls[1][0]).toStrictEqual({ ...PERIOD, categories: ['Learning'] })
    // The current draft stays visible but read-only; Save summary is disabled.
    expect(field().value).toBe(DRAFT_TEXT)
    expect(field().readOnly).toBe(true)
    expect(sourceLine().textContent).toContain('All categories')
    expect(saveButton().disabled).toBe(true)
    expect(draftButton().textContent).toBe('Drafting…')
    expect(progress().textContent).toBe(PROGRESS)

    await act(async () => {
      answer.resolve(makeSummary({ ...PERIOD, categories: ['Learning'] }, 'Second draft', 'second-id'))
    })

    expect(field().value).toBe('Second draft')
    expect(field().readOnly).toBe(false)
    expect(sourceLine().textContent).toBe('Entries from 1 Jan 2026 – 30 Jun 2026 · Learning · All tags')
    expect(document.activeElement).toBe(sourceLine())
    // Saving now saves the new summary.
    await type(field(), 'Second draft, edited')
    await click(saveButton())
    expect(updateSummary).toHaveBeenCalledWith('second-id', { text: 'Second draft, edited' })
  })

  it('test_fr_r3_draft_again_with_unsaved_changes_asks_first', async () => {
    await renderWithDraft()
    await type(field(), 'Unsaved edit')

    await click(draftButton())

    const dialog = openDialog()
    expect(dialog).not.toBeNull()
    expect(within(dialog as HTMLElement).getByRole('heading', { name: 'Discard changes?' })).toBeTruthy()
    expect(generateSummary).toHaveBeenCalledTimes(1)

    // Keep editing: nothing changes.
    await click(within(dialog as HTMLElement).getByRole('button', { name: 'Keep editing' }))
    expect(openDialog()).toBeNull()
    expect(field().value).toBe('Unsaved edit')
    expect(generateSummary).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(draftButton())

    // Discard: the last saved text comes back and drafting starts.
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)
    await click(draftButton())
    await click(within(openDialog() as HTMLElement).getByRole('button', { name: 'Discard' }))
    expect(openDialog()).toBeNull()
    expect(generateSummary).toHaveBeenCalledTimes(2)
    expect(field().value).toBe(DRAFT_TEXT)
    expect(draftButton().textContent).toBe('Drafting…')

    await act(async () => {
      answer.resolve(makeSummary(PERIOD, 'Second draft', 'second-id'))
    })
    expect(field().value).toBe('Second draft')
  })

  it('test_fr_r3_failed_draft_again_keeps_the_earlier_draft', async () => {
    await renderWithDraft()
    await type(field(), 'Unsaved edit')
    generateSummary.mockRejectedValue(new AiUnavailableError('server text', 503))
    // A click that does not focus the button (Safari): focus is still in the text field.
    field().focus()
    // The browser gives focus back to what had it when the dialog opened.
    const focusedAtOpen: (Element | null)[] = []
    const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (
      this: HTMLDialogElement,
    ) {
      focusedAtOpen.push(document.activeElement)
      this.setAttribute('open', '')
    })

    await click(draftButton())
    expect(focusedAtOpen).toEqual([draftButton()])
    await click(within(openDialog() as HTMLElement).getByRole('button', { name: 'Discard' }))
    showModal.mockRestore()

    expect(field().value).toBe(DRAFT_TEXT)
    expect(sourceLine().textContent).toBe('Entries from 1 Jan 2026 – 30 Jun 2026 · All categories · All tags')
    expect(infoNotice()).toBe("The summary couldn't be written right now. Please try again later.")
    expect(draftButton().disabled).toBe(false)
    expect(saveButton().disabled).toBe(false)
    expect(document.activeElement).toBe(draftButton())
  })
})

describe('filters and leaving (FR-R3)', () => {
  it('test_fr_r3_a_filter_change_never_changes_the_draft_or_asks', async () => {
    const { router } = await renderWithDraft()
    await type(field(), 'Unsaved edit')

    await click(chip('Feedback'))
    await type(screen.getByLabelText('Start date'), '2026-03-01')

    expect(openDialog()).toBeNull()
    expect(router.state.location.search).toContain('category=Feedback')
    expect(router.state.location.search).toContain('start_date=2026-03-01')
    expect(field().value).toBe('Unsaved edit')
    expect(sourceLine().textContent).toBe('Entries from 1 Jan 2026 – 30 Jun 2026 · All categories · All tags')
  })

  it('test_fr_r3_the_review_link_keeps_the_draft_and_does_not_ask', async () => {
    const { router } = await renderWithDraft()
    await type(field(), 'Unsaved edit')

    await click(navLink('Review'))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/review')
    expect(field().value).toBe('Unsaved edit')
  })

  it('test_fr_r3_leaving_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderWithDraft()
    await type(field(), 'Unsaved edit')

    await click(navLink('Entries'))

    const dialog = openDialog() as HTMLElement
    expect(within(dialog).getByRole('heading', { name: 'Discard changes?' })).toBeTruthy()
    expect(router.state.location.pathname).toBe('/review')
    await click(within(dialog).getByRole('button', { name: 'Keep editing' }))
    expect(router.state.location.pathname).toBe('/review')
    expect(field().value).toBe('Unsaved edit')

    await click(navLink('Entries'))
    await click(within(openDialog() as HTMLElement).getByRole('button', { name: 'Discard' }))
    expect(router.state.location.pathname).toBe('/')
    expect(updateSummary).not.toHaveBeenCalled()
  })

  it('test_fr_r3_back_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderWithHistory(['/', PERIOD_PATH])
    generateSummary.mockResolvedValueOnce(makeSummary(PERIOD))
    await click(draftButton())
    await type(field(), 'Unsaved edit')

    await act(async () => {
      await router.navigate(-1)
    })

    expect(openDialog()).not.toBeNull()
    expect(router.state.location.pathname).toBe('/review')
  })

  it('test_fr_r3_without_unsaved_changes_the_page_is_left_at_once', async () => {
    const { router } = await renderWithDraft()

    await click(navLink('Entries'))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/')
  })

  it('test_fr_r3_closing_the_tab_with_unsaved_changes_shows_the_browser_prompt', async () => {
    await renderWithDraft()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)

    await type(field(), 'Unsaved edit')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
  })

  it('test_fr_r3_logging_out_never_asks', async () => {
    setViewport('phone')
    const { router } = await renderWithDraft()
    await type(field(), 'Unsaved edit')

    await click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('button', { name: 'More' }))
    await click(screen.getByRole('button', { name: 'Log out' }))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_r3_the_login_redirect_never_asks', async () => {
    const { router } = await renderWithDraft()
    await type(field(), 'Unsaved edit')
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_r3_a_reload_shows_the_panel_without_a_draft', async () => {
    const { unmount } = await renderWithDraft()
    unmount()

    await renderReview()

    expect(draftButton().textContent).toBe('Draft summary')
    expect(within(panel()).queryByLabelText('Summary text')).toBeNull()
  })
})

describe('when drafting fails (FR-R3, §7.4, §8)', () => {
  it.each([
    [
      'no_matching_entries',
      new NoMatchingEntriesError('server text', 422),
      'No entries match these filters, so no summary was created.',
    ],
    [
      'ai_unavailable',
      new AiUnavailableError('server text', 503),
      "The summary couldn't be written right now. Please try again later.",
    ],
    [
      'the user limit',
      new LimitReachedError('server text', 429, 'user_summaries'),
      "You've used today's summaries. They're available again after midnight UTC.",
    ],
    [
      'the global limit',
      new LimitReachedError('server text', 429, 'global'),
      "Winlog has reached today's AI limit for everyone. Try again after midnight UTC.",
    ],
    [
      'a limit naming no limit',
      new LimitReachedError('server text', 429, null),
      "The summary couldn't be written right now. Please try again later.",
    ],
    [
      'another limit',
      new LimitReachedError('server text', 429, 'user_suggestions'),
      "The summary couldn't be written right now. Please try again later.",
    ],
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['another error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r3_failure_notice_for_%s_and_the_page_stays_usable', async (_name, error, notice) => {
    await renderReview()
    generateSummary.mockRejectedValue(error)
    draftButton().focus()

    await click(draftButton())

    expect(infoNotice()).toBe(notice)
    expect(panel().querySelector('.message--info')?.getAttribute('role')).toBe('status')
    expect(screen.queryByText('server text')).toBeNull()
    // The panel is ready again, with its line back and focus on the button.
    expect(draftButton().textContent).toBe('Draft summary')
    expect(draftButton().disabled).toBe(false)
    expect(buttonHint()).toBe('Draft a summary of the 3 entries shown.')
    expect(progress().textContent).toBe('')
    expect(document.activeElement).toBe(draftButton())
    // The rest of the page keeps working, and a filter change removes the notice.
    listEntries.mockClear()
    await click(chip('Feedback'))
    expect(listEntries).toHaveBeenCalledTimes(1)
    expect(infoNotice()).toBe('')
  })

  it('test_fr_r3_the_notice_goes_when_a_new_draft_starts', async () => {
    await renderReview()
    generateSummary.mockRejectedValueOnce(new AiUnavailableError('server text', 503))
    await click(draftButton())
    expect(infoNotice()).not.toBe('')
    const answer = deferred<Summary>()
    generateSummary.mockReturnValue(answer.promise)

    await click(draftButton())

    expect(infoNotice()).toBe('')
    expect(progress().textContent).toBe(PROGRESS)
  })

  it('test_fr_r3_an_expired_login_opens_the_login_page', async () => {
    const { router } = await renderReview()
    generateSummary.mockImplementation(async () => {
      // As the client does on a 401: remove the session, open the login page, then throw.
      removeTestSession()
      registeredRedirect()()
      throw new NotAuthenticatedError('server text', 401)
    })

    await click(draftButton())

    expect(router.state.location.pathname).toBe('/login')
    expect(openDialog()).toBeNull()
  })
})
