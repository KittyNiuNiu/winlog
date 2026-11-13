import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import {
  NetworkError,
  NotAuthenticatedError,
  NotFoundError,
  UnknownError,
  ValidationError,
  type Summary,
  type SummaryFilter,
} from '../api/index.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { routes } from '../routes.tsx'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

// One saved summary (#33): its lines, the always editable text with Save summary (FR-R5),
// Copy (FR-R6) and Delete (FR-R5), and that editing never changes an entry (§7.4). The API
// client and the clipboard are mocked; this page makes no AI call. Tests run in Sydney
// (vite.config.ts).

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    getSummary: vi.fn(),
    updateSummary: vi.fn(),
    deleteSummary: vi.fn(),
    listSummaries: vi.fn(),
    generateSummary: vi.fn(),
    listEntries: vi.fn(),
    getEntry: vi.fn(),
    createEntry: vi.fn(),
    updateEntry: vi.fn(),
    deleteEntry: vi.fn(),
    listTags: vi.fn(),
    logout: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const getSummary = vi.mocked(api.getSummary)
const updateSummary = vi.mocked(api.updateSummary)
const deleteSummary = vi.mocked(api.deleteSummary)
const listSummaries = vi.mocked(api.listSummaries)

const SUMMARY_ID = '6f1c2a5e-0000-4000-8000-000000000033'
const SUMMARY_PATH = `/summaries/${SUMMARY_ID}`
const FILTER: SummaryFilter = {
  period_start: '2026-01-01',
  period_end: '2026-06-30',
  categories: ['Learning', 'Achievement'],
}
const TEXT = 'Mock summary\n\nLed the incident review.\nShipped the export.'

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const GONE = "This summary no longer exists, so your changes can't be saved."
const NOTE = 'Editing changes only this summary. Your entries stay as they are.'
const COPY_FAILED = "Couldn't copy. Select the text and copy it manually."

function makeSummary(overrides: Partial<Summary> = {}): Summary {
  return {
    id: SUMMARY_ID,
    text: TEXT,
    filter: FILTER,
    created_at: '2026-11-12T22:30:00Z',
    updated_at: '2026-11-12T22:30:00Z',
    ...overrides,
  }
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

async function renderPage(path = SUMMARY_PATH) {
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

function page(): HTMLElement {
  return document.querySelector('.summary-page') as HTMLElement
}

function field(): HTMLTextAreaElement {
  return screen.getByLabelText('Summary text') as HTMLTextAreaElement
}

function pageButton(name: RegExp): HTMLButtonElement {
  // Outside the dialogs.
  const buttons = within(page()).getAllByRole('button', { name, hidden: true })
  const button = buttons.find((element) => element.closest('dialog') === null)
  if (button === undefined) {
    throw new Error(`no page button ${String(name)}`)
  }
  return button as HTMLButtonElement
}

function saveButton(): HTMLButtonElement {
  return pageButton(/^(Save summary|Saving…)$/)
}

function copyButton(): HTMLButtonElement {
  return pageButton(/^(Copy|Copied)$/)
}

function deleteButton(): HTMLButtonElement {
  return pageButton(/^Delete$/)
}

function openDialog(): HTMLDialogElement | null {
  return document.querySelector<HTMLDialogElement>('dialog[open]')
}

function dialogButton(name: string | RegExp): HTMLButtonElement {
  return within(openDialog() as HTMLElement).getByRole('button', { name }) as HTMLButtonElement
}

function backLinks(): HTMLElement[] {
  return within(page()).queryAllByRole('link', { name: 'Back to summaries' })
}

function errorSlot(): string {
  return page().querySelector('.summary-page__messages .message--error')?.textContent ?? ''
}

function savedBand(): string {
  return page().querySelector('.summary-page__messages .saved-region')?.textContent ?? ''
}

function copiedStatus(): HTMLElement {
  return page().querySelector('.visually-hidden[role="status"]') as HTMLElement
}

function primaryButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('.button--primary'))
}

function navLink(name: string): HTMLElement {
  return within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name })
}

/** The redirect the API client calls after a "not authenticated" response. */
function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

/** Puts a mocked Clipboard API on `navigator`, or removes it (`undefined`). */
function mockClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
  const clipboard = writeText === undefined ? undefined : { writeText: vi.fn(writeText) }
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true })
  return clipboard?.writeText
}

function expectNoEntryEndpointCalled(): void {
  expect(api.listEntries).not.toHaveBeenCalled()
  expect(api.getEntry).not.toHaveBeenCalled()
  expect(api.createEntry).not.toHaveBeenCalled()
  expect(api.updateEntry).not.toHaveBeenCalled()
  expect(api.deleteEntry).not.toHaveBeenCalled()
  expect(api.generateSummary).not.toHaveBeenCalled()
}

beforeEach(() => {
  storeTestSession()
  getSummary.mockResolvedValue(makeSummary())
  updateSummary.mockImplementation(async (id, body) => makeSummary({ id, text: body.text }))
  deleteSummary.mockResolvedValue(undefined)
  listSummaries.mockResolvedValue({ summaries: [] })
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [] })
  vi.mocked(api.listTags).mockResolvedValue({ tags: [] })
  vi.mocked(api.logout).mockImplementation(async () => removeTestSession())
  mockClipboard(async () => {})
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
  vi.unstubAllEnvs()
  Reflect.deleteProperty(navigator, 'clipboard')
})

describe('the summary page (FR-R5, §7.4)', () => {
  it('test_fr_r5_page_shows_its_lines_the_note_and_the_text', async () => {
    await renderPage()

    expect(getSummary).toHaveBeenCalledWith(SUMMARY_ID)
    expect(screen.getByRole('heading', { level: 1, name: 'Summary' })).toBeTruthy()
    expect(backLinks()).toHaveLength(1)
    expect(backLinks()[0].getAttribute('href')).toBe('/summaries')
    expect(within(page()).getByText(/^Entries from /).textContent).toBe(
      'Entries from 1 Jan 2026 – 30 Jun 2026 · Achievement, Learning · All tags',
    )
    // 22:30 UTC on 12 November is 09:30 on 13 November in Sydney.
    expect(within(page()).getByText(/^Created /).textContent).toBe('Created 13 Nov 2026')
    // The note is the field's hint, linked to it.
    const hint = within(page()).getByText(NOTE)
    expect(field().getAttribute('aria-describedby')?.split(' ')).toContain(hint.id)
    // Always editable, with its line breaks.
    expect(field().tagName).toBe('TEXTAREA')
    expect(field().value).toBe(TEXT)
    expect(field().readOnly).toBe(false)
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })

  it('test_fr_r4_period_dates_on_the_page_are_not_shifted', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    getSummary.mockResolvedValue(
      makeSummary({ filter: { period_start: '2026-01-01', period_end: '2026-01-31' }, created_at: '2026-01-01T03:00:00Z' }),
    )
    await renderPage()

    expect(within(page()).getByText(/^Entries from /).textContent).toBe(
      'Entries from 1 Jan 2026 – 31 Jan 2026 · All categories · All tags',
    )
    // The creation time is a moment: in Los Angeles it was still 31 December.
    expect(within(page()).getByText(/^Created /).textContent).toBe('Created 31 Dec 2025')
  })

  it('test_fr_r5_save_summary_is_the_one_plum_button_copy_and_delete_are_secondary_with_icons', async () => {
    await renderPage()

    expect(primaryButtons()).toEqual([saveButton()])
    for (const [button, label] of [
      [copyButton(), 'Copy'],
      [deleteButton(), 'Delete'],
    ] as const) {
      expect(button.classList.contains('button--secondary')).toBe(true)
      expect(button.textContent).toBe(label)
      expect(button.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    }
    // The order: Save summary, Copy, then Delete.
    expect(saveButton().compareDocumentPosition(copyButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(copyButton().compareDocumentPosition(deleteButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(field().compareDocumentPosition(saveButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each(['phone', 'laptop'] as const)('test_fr_r5_summaries_is_current_on_the_summary_page_%s', async (width) => {
    setViewport(width)
    await renderPage()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    if (width === 'laptop') {
      expect(within(nav).getByRole('link', { name: 'Summaries' }).getAttribute('aria-current')).toBe('page')
    } else {
      expect(within(nav).getByRole('button', { name: 'More' }).classList.contains('shell__pill--current')).toBe(true)
    }
  })

  it('test_fr_r5_back_to_summaries_opens_the_list', async () => {
    const { router } = await renderPage()

    await click(backLinks()[0])

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/summaries')
  })
})

describe('saving (FR-R5)', () => {
  it('test_fr_r5_save_edited_summary', async () => {
    await renderPage()
    const answer = deferred<Summary>()
    updateSummary.mockReturnValue(answer.promise)
    await type(field(), '  My own words.\nSecond line.  ')
    saveButton().focus()

    await click(saveButton())

    expect(updateSummary).toHaveBeenCalledTimes(1)
    // Exactly as typed.
    expect(updateSummary).toHaveBeenCalledWith(SUMMARY_ID, { text: '  My own words.\nSecond line.  ' })
    // While saving: Saving…, the field read-only, Delete disabled, Copy still usable.
    expect(saveButton().textContent).toBe('Saving…')
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(saveButton().getAttribute('aria-disabled')).toBe('true')
    expect(saveButton().disabled).toBe(false)
    expect(field().readOnly).toBe(true)
    expect(deleteButton().disabled).toBe(true)
    expect(copyButton().disabled).toBe(false)
    await click(saveButton())
    await type(field(), 'Typed while saving')
    expect(updateSummary).toHaveBeenCalledTimes(1)
    expect(field().value).toBe('  My own words.\nSecond line.  ')

    await act(async () => {
      answer.resolve(makeSummary({ text: '  My own words.\nSecond line.  ' }))
    })

    const savedRegion = page().querySelector('.summary-page__messages .saved-region') as HTMLElement
    expect(savedRegion.getAttribute('role')).toBe('status')
    expect(savedBand()).toBe('Summary saved.')
    expect(field().value).toBe('  My own words.\nSecond line.  ')
    expect(field().readOnly).toBe(false)
    expect(deleteButton().disabled).toBe(false)
    expect(document.activeElement).toBe(saveButton())
  })

  it('test_fr_r5_after_saving_leaving_does_not_ask', async () => {
    const { router } = await renderPage()
    await type(field(), 'Edited')
    await click(saveButton())

    await click(backLinks()[0])

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/summaries')
  })

  it.each(['', '   \n\t '])('test_fr_r5_empty_text_is_not_sent_%#', async (empty) => {
    await renderPage()
    await type(field(), empty)

    await click(saveButton())

    expect(updateSummary).not.toHaveBeenCalled()
    expect(within(page()).getByText('Write your summary, then save.')).toBeTruthy()
    expect(field().getAttribute('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(field())

    await type(field(), 'Now with words')
    expect(within(page()).queryByText('Write your summary, then save.')).toBeNull()
    expect(field().getAttribute('aria-invalid')).toBe('false')
  })

  it.each([
    ['not_found', new NotFoundError('server text', 404), GONE],
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['another error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r5_failed_save_keeps_the_text_after_%s', async (_name, error, message) => {
    const { router } = await renderPage()
    updateSummary.mockRejectedValue(error)
    await type(field(), 'Edited text')
    saveButton().focus()

    await click(saveButton())

    expect(errorSlot()).toBe(message)
    expect(page().querySelector('.summary-page__messages .message--error')?.getAttribute('role')).toBe('alert')
    expect(within(page()).queryByText('server text')).toBeNull()
    expect(field().value).toBe('Edited text')
    expect(savedBand()).toBe('')
    expect(document.activeElement).toBe(saveButton())
    // Still unsaved.
    await click(backLinks()[0])
    expect(openDialog()).not.toBeNull()
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
  })

  it('test_fr_r5_an_expired_login_while_saving_opens_the_login_page', async () => {
    const { router } = await renderPage()
    updateSummary.mockImplementation(async () => {
      removeTestSession()
      registeredRedirect()()
      throw new NotAuthenticatedError('server text', 401)
    })
    await type(field(), 'Edited text')

    await click(saveButton())

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_r5_saving_never_calls_an_entry_endpoint', async () => {
    await renderPage()
    await type(field(), 'Edited text')
    await click(saveButton())

    expect(updateSummary).toHaveBeenCalledTimes(1)
    expectNoEntryEndpointCalled()
  })
})

describe('leaving with unsaved changes (FR-R5)', () => {
  it('test_fr_r5_back_to_summaries_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')

    await click(backLinks()[0])

    const dialog = openDialog() as HTMLElement
    expect(within(dialog).getByRole('heading', { name: 'Discard changes?' })).toBeTruthy()
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
    await click(within(dialog).getByRole('button', { name: 'Keep editing' }))
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
    expect(field().value).toBe('Unsaved edit')

    await click(backLinks()[0])
    await click(dialogButton('Discard'))
    expect(router.state.location.pathname).toBe('/summaries')
    expect(updateSummary).not.toHaveBeenCalled()
  })

  it('test_fr_r5_the_navigation_with_unsaved_changes_asks_first', async () => {
    setViewport('laptop')
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')

    await click(navLink('Entries'))

    expect(openDialog()).not.toBeNull()
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
  })

  it('test_fr_r5_browser_back_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderWithHistory(['/summaries', SUMMARY_PATH])
    await type(field(), 'Unsaved edit')

    await act(async () => {
      await router.navigate(-1)
    })

    expect(openDialog()).not.toBeNull()
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
  })

  it('test_fr_r5_closing_the_tab_with_unsaved_changes_shows_the_browser_prompt', async () => {
    await renderPage()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)

    await type(field(), 'Unsaved edit')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
  })

  it('test_fr_r5_logging_out_never_asks', async () => {
    setViewport('phone')
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')

    await click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('button', { name: 'More' }))
    await click(screen.getByRole('button', { name: 'Log out' }))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_r5_the_login_redirect_never_asks', async () => {
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })
})

describe('copying (FR-R6)', () => {
  it('test_fr_r6_copy_summary_text', async () => {
    vi.useFakeTimers()
    const writeText = mockClipboard(async () => {})
    await renderPage()
    copyButton().focus()

    await click(copyButton())

    // Plain text, line breaks included.
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(writeText).toHaveBeenCalledWith(TEXT)
    expect(copyButton().textContent).toBe('Copied')
    expect(copyButton().querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    expect(copiedStatus().textContent).toBe('Copied')
    expect(document.activeElement).toBe(copyButton())
    expect(errorSlot()).toBe('')

    await act(async () => {
      vi.advanceTimersByTime(1_999)
    })
    expect(copyButton().textContent).toBe('Copied')
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(copyButton().textContent).toBe('Copy')
    expect(copiedStatus().textContent).toBe('')
    expect(document.activeElement).toBe(copyButton())
  })

  it('test_fr_r6_copy_takes_the_text_in_the_field_with_unsaved_edits', async () => {
    const writeText = mockClipboard(async () => {})
    await renderPage()
    await type(field(), 'Unsaved\nedit')

    await click(copyButton())

    expect(writeText).toHaveBeenCalledWith('Unsaved\nedit')
    expect(updateSummary).not.toHaveBeenCalled()
  })

  it.each([
    ['the browser refuses', async () => Promise.reject(new DOMException('Denied', 'NotAllowedError'))],
    ['there is no Clipboard API', undefined],
  ])('test_fr_r6_copy_fails_when_%s', async (_case, writeText) => {
    mockClipboard(writeText)
    await renderPage()
    copyButton().focus()

    await click(copyButton())

    expect(errorSlot()).toBe(COPY_FAILED)
    expect(copyButton().textContent).toBe('Copy')
    expect(copiedStatus().textContent).toBe('')
    expect(document.activeElement).toBe(copyButton())
    // The text stays in the field, where it can be selected.
    expect(field().value).toBe(TEXT)
    expect(field().readOnly).toBe(false)
  })

  it('test_fr_r6_the_copy_error_goes_at_the_next_copy', async () => {
    mockClipboard(async () => Promise.reject(new Error('Denied')))
    await renderPage()
    await click(copyButton())
    expect(errorSlot()).toBe(COPY_FAILED)

    mockClipboard(async () => {})
    await click(copyButton())

    expect(errorSlot()).toBe('')
    expect(copyButton().textContent).toBe('Copied')
  })

  it.each(['', '  \n\t '])('test_fr_r6_copy_is_disabled_while_the_text_is_empty_%#', async (empty) => {
    const writeText = mockClipboard(async () => {})
    await renderPage()
    expect(copyButton().disabled).toBe(false)

    await type(field(), empty)

    expect(copyButton().disabled).toBe(true)
    await click(copyButton())
    expect(writeText).not.toHaveBeenCalled()

    await type(field(), 'Words')
    expect(copyButton().disabled).toBe(false)
  })
})

describe('deleting (FR-R5)', () => {
  it('test_fr_r5_delete_asks_for_confirmation', async () => {
    await renderPage()
    expect(openDialog()).toBeNull()

    await click(deleteButton())

    const dialog = openDialog() as HTMLDialogElement
    expect(within(dialog).getByRole('heading', { level: 2 }).textContent).toBe('Delete this summary?')
    expect(document.getElementById(dialog.getAttribute('aria-labelledby') ?? '')?.textContent).toBe(
      'Delete this summary?',
    )
    expect(document.getElementById(dialog.getAttribute('aria-describedby') ?? '')?.textContent).toBe(
      "This can't be undone. Your entries are not affected.",
    )
    const buttons = within(dialog).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Cancel', 'Delete summary'])
    for (const button of buttons) {
      expect(button.classList.contains('button--secondary')).toBe(true)
    }
    expect(document.activeElement).toBe(dialogButton('Cancel'))
    expect(deleteSummary).not.toHaveBeenCalled()
  })

  it('test_fr_r5_cancel_keeps_the_summary', async () => {
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')
    await click(deleteButton())

    await click(dialogButton('Cancel'))

    expect(openDialog()).toBeNull()
    expect(deleteSummary).not.toHaveBeenCalled()
    expect(field().value).toBe('Unsaved edit')
    expect(document.activeElement).toBe(deleteButton())
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
  })

  it('test_fr_r5_escape_keeps_the_summary', async () => {
    await renderPage()
    await click(deleteButton())

    await act(async () => {
      fireEvent.keyDown(openDialog() as HTMLElement, { key: 'Escape' })
    })

    expect(openDialog()).toBeNull()
    expect(deleteSummary).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(deleteButton())
  })

  it('test_fr_r5_while_deleting_nothing_else_works', async () => {
    await renderPage()
    const answer = deferred<void>()
    deleteSummary.mockReturnValue(answer.promise)
    await click(deleteButton())

    await click(dialogButton('Delete summary'))

    const busy = dialogButton(/^Deleting…$/)
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(busy.getAttribute('aria-disabled')).toBe('true')
    expect(busy.disabled).toBe(false)
    await click(busy)
    await click(dialogButton('Cancel'))
    await act(async () => {
      fireEvent.keyDown(openDialog() as HTMLElement, { key: 'Escape' })
    })
    await act(async () => {
      openDialog()?.dispatchEvent(new Event('cancel', { cancelable: true }))
    })
    expect(openDialog()).not.toBeNull()
    expect(deleteSummary).toHaveBeenCalledTimes(1)
    expect(deleteSummary).toHaveBeenCalledWith(SUMMARY_ID)

    await act(async () => {
      answer.resolve()
    })
  })

  it('test_fr_r5_delete_opens_the_list_with_summary_deleted_without_asking', async () => {
    listSummaries.mockResolvedValue({ summaries: [makeSummary({ id: 'other' })] })
    const { router } = await renderWithHistory(['/review', SUMMARY_PATH])
    // Unsaved edits do not make it ask.
    await type(field(), 'Unsaved edit')
    await click(deleteButton())

    await click(dialogButton('Delete summary'))

    expect(deleteSummary).toHaveBeenCalledWith(SUMMARY_ID)
    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/summaries')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(screen.getByRole('heading', { level: 1, name: 'Summaries' })).toBeTruthy()
    expect(document.querySelector('.summaries-page > .saved-region')?.textContent).toBe('Summary deleted.')
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Summaries' }))
    expectNoEntryEndpointCalled()

    // The deleted page was replaced, so Back goes to the page before it.
    await act(async () => {
      await router.navigate(-1)
    })
    expect(router.state.location.pathname).toBe('/review')
  })

  it('test_fr_r5_delete_of_a_summary_already_gone_opens_the_list_with_already_deleted', async () => {
    deleteSummary.mockRejectedValue(new NotFoundError('server text', 404))
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')
    await click(deleteButton())

    await click(dialogButton('Delete summary'))

    expect(openDialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/summaries')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(document.querySelector('.summaries-page__notice')?.textContent).toBe('This summary was already deleted.')
    expect(document.querySelector('.summaries-page > .saved-region')?.textContent).toBe('')
    expect(screen.queryByText('server text')).toBeNull()
  })

  it.each([
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['another error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r5_a_failed_delete_stays_in_the_dialog_after_%s', async (_case, error, message) => {
    deleteSummary.mockRejectedValueOnce(error)
    const { router } = await renderPage()
    await type(field(), 'Unsaved edit')
    await click(deleteButton())

    await click(dialogButton('Delete summary'))

    const dialog = openDialog() as HTMLDialogElement
    expect(dialog).not.toBeNull()
    expect(within(dialog).getByRole('alert').textContent).toBe(message)
    expect(within(dialog).queryByText('server text')).toBeNull()
    expect(document.activeElement).toBe(dialogButton('Delete summary'))
    expect(router.state.location.pathname).toBe(SUMMARY_PATH)
    expect(field().value).toBe('Unsaved edit')

    // A retry works.
    await click(dialogButton('Delete summary'))
    expect(deleteSummary).toHaveBeenCalledTimes(2)
    expect(router.state.location.pathname).toBe('/summaries')
  })

  it('test_fr_r5_cancel_after_a_failed_delete_keeps_the_summary', async () => {
    deleteSummary.mockRejectedValueOnce(new NetworkError())
    await renderPage()
    await click(deleteButton())
    await click(dialogButton('Delete summary'))

    await click(dialogButton('Cancel'))

    expect(openDialog()).toBeNull()
    expect(field().value).toBe(TEXT)
    expect(document.activeElement).toBe(deleteButton())
    // Opened again, the dialog has no old error.
    await click(deleteButton())
    expect(within(openDialog() as HTMLElement).queryByRole('alert')?.textContent ?? '').toBe('')
  })

  it('test_fr_r5_deleting_never_calls_an_entry_endpoint', async () => {
    await renderPage()
    await click(deleteButton())
    await click(dialogButton('Delete summary'))

    expect(deleteSummary).toHaveBeenCalledTimes(1)
    expectNoEntryEndpointCalled()
  })
})

describe('not found, loading and errors (FR-R5, §12)', () => {
  it.each([
    ['does not exist or belongs to another user', new NotFoundError('Not found.', 404)],
    [
      'has an invalid id',
      new ValidationError('The request has invalid fields.', 422, [
        { field: 'summaryId', reason: 'Input should be a valid UUID' },
      ]),
    ],
  ])('test_fr_r5_a_summary_that_%s_shows_that_it_does_not_exist', async (_case, error) => {
    getSummary.mockRejectedValue(error)
    const { router } = await renderPage('/summaries/not-a-uuid')

    expect(screen.getByRole('heading', { level: 1, name: 'Summary' })).toBeTruthy()
    const status = screen.getByText("This summary doesn't exist.", { exact: false })
    expect(status.textContent).toBe("This summary doesn't exist. Back to summaries")
    const link = within(status).getByRole('link', { name: 'Back to summaries' })
    expect(link.getAttribute('href')).toBe('/summaries')
    // One back link, not two.
    expect(backLinks()).toEqual([link])
    expect(screen.queryByLabelText('Summary text')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()

    await click(link)
    expect(router.state.location.pathname).toBe('/summaries')
  })

  it('test_fr_r5_another_validation_error_is_a_load_error', async () => {
    getSummary.mockRejectedValueOnce(
      new ValidationError('The request has invalid fields.', 422, [{ field: 'other', reason: 'x' }]),
    )
    await renderPage()

    expect(screen.getByRole('alert').textContent).toBe(GENERIC_MESSAGE)
    expect(screen.queryByText("This summary doesn't exist.", { exact: false })).toBeNull()
  })

  it('test_fr_r5_loading_shows_progress_then_the_waking_up_hint', async () => {
    vi.useFakeTimers()
    const answer = deferred<Summary>()
    getSummary.mockReturnValue(answer.promise)
    await renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Summary' })).toBeTruthy()
    expect(backLinks()).toHaveLength(1)
    expect(screen.getByText('Loading summary…').getAttribute('role')).toBe('status')
    expect(screen.queryByLabelText('Summary text')).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()

    await act(async () => {
      answer.resolve(makeSummary())
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    expect(field().value).toBe(TEXT)
  })

  it.each([
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    ['a server error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_r5_a_load_error_shows_a_message_and_try_again_retries (%s)', async (_case, error, message) => {
    getSummary.mockRejectedValueOnce(error)
    await renderPage()

    expect(screen.getByRole('alert').textContent).toBe(message)
    expect(screen.queryByText('server text')).toBeNull()
    expect(screen.queryByLabelText('Summary text')).toBeNull()
    expect(backLinks()).toHaveLength(1)

    await click(screen.getByRole('button', { name: 'Try again' }))

    expect(getSummary).toHaveBeenCalledTimes(2)
    expect(field().value).toBe(TEXT)
  })

  it('test_fr_r5_an_expired_login_while_loading_opens_the_login_page', async () => {
    getSummary.mockReturnValue(new Promise(() => {}))
    const { router } = await renderPage()
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: SUMMARY_PATH })
  })
})

// Keyboard focus (#84): the busy "Save summary" and "Delete summary" keep focus, and a
// failed retry focuses the new "Try again" unless the user moved on.
describe('keyboard focus on the summary page (FR-R5, #84)', () => {
  function tryAgain(): HTMLButtonElement {
    return screen.getByRole('button', { name: 'Try again' }) as HTMLButtonElement
  }

  async function pressTryAgain(): Promise<void> {
    tryAgain().focus()
    await click(tryAgain())
  }

  it('test_fr_r5_busy_save_summary_keeps_focus_throughout_a_failure', async () => {
    await renderPage()
    const answer = deferred<Summary>()
    updateSummary.mockReturnValue(answer.promise)
    await type(field(), 'Edited')
    saveButton().focus()

    await click(saveButton())
    expect(saveButton().textContent).toBe('Saving…')
    // Focusable while busy: a natively disabled button would drop focus in a browser.
    expect(saveButton().disabled).toBe(false)
    expect(document.activeElement).toBe(saveButton())
    await act(async () => {
      answer.reject(new NetworkError())
    })

    expect(errorSlot()).toBe(NETWORK_MESSAGE)
    expect(document.activeElement).toBe(saveButton())
  })

  it('test_fr_r5_busy_delete_summary_keeps_focus_and_after_a_failure', async () => {
    await renderPage()
    const answer = deferred<void>()
    deleteSummary.mockReturnValue(answer.promise)
    await click(deleteButton())
    dialogButton('Delete summary').focus()

    await click(dialogButton('Delete summary'))
    const busy = dialogButton(/^Deleting…$/)
    expect(busy.disabled).toBe(false)
    expect(document.activeElement).toBe(busy)
    await act(async () => {
      answer.reject(new NetworkError())
    })

    expect(openDialog()).not.toBeNull()
    expect(document.activeElement).toBe(dialogButton('Delete summary'))
  })

  it('test_fr_r5_failed_retry_moves_focus_to_the_new_try_again', async () => {
    getSummary.mockRejectedValueOnce(new NetworkError())
    await renderPage()
    // The first failure moves no focus.
    expect(document.activeElement).toBe(document.body)
    const first = tryAgain()
    const answer = deferred<Summary>()
    getSummary.mockReturnValueOnce(answer.promise)

    await pressTryAgain()
    expect(screen.getByText('Loading summary…')).toBeTruthy()
    await act(async () => {
      answer.reject(new NetworkError())
    })

    expect(tryAgain()).not.toBe(first)
    expect(document.activeElement).toBe(tryAgain())
  })

  it('test_fr_r5_failed_retry_keeps_focus_where_the_user_moved', async () => {
    getSummary.mockRejectedValueOnce(new NetworkError())
    await renderPage()
    const answer = deferred<Summary>()
    getSummary.mockReturnValueOnce(answer.promise)

    await pressTryAgain()
    navLink('Review').focus()
    await act(async () => {
      answer.reject(new NetworkError())
    })

    expect(tryAgain()).toBeTruthy()
    expect(document.activeElement).toBe(navLink('Review'))
  })

  it('test_fr_r5_successful_retry_moves_no_focus', async () => {
    getSummary.mockRejectedValueOnce(new NetworkError())
    await renderPage()

    await pressTryAgain()

    expect(field().value).toBe(TEXT)
    expect(document.activeElement).toBe(document.body)
  })
})

describe('maximum size of the summary text (#43, FR-R5)', () => {
  function counter(): HTMLElement | null {
    return document.getElementById(`${field().id}-counter`)
  }

  it('test_fr_r5_counter_from_8000_characters', async () => {
    getSummary.mockResolvedValue(makeSummary({ text: 's'.repeat(7999) }))
    await renderPage()
    expect(counter()).toBeNull()

    await type(field(), 's'.repeat(8000))
    expect(counter()?.textContent).toContain('8,000 / 10,000')
    expect(field().getAttribute('aria-invalid')).toBe('false')
  })

  it('test_fr_r5_save_over_10000_characters_sends_nothing', async () => {
    getSummary.mockResolvedValue(makeSummary())
    await renderPage()
    await type(field(), 'a'.repeat(10001))

    await click(saveButton())

    expect(updateSummary).not.toHaveBeenCalled()
    expect(screen.getByText('Shorten the summary to 10,000 characters, then save.')).toBeTruthy()
    expect(document.activeElement).toBe(field())
  })

  it('test_fr_r5_summary_saved_before_the_limit_shows_the_over_limit_counter_copies_whole_and_saves_shortened', async () => {
    const long = 's'.repeat(12000)
    getSummary.mockResolvedValue(makeSummary({ text: long }))
    updateSummary.mockImplementation(async (_id, body) => makeSummary({ text: body.text }))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await renderPage()

    expect(counter()?.textContent).toContain('12,000 / 10,000')
    expect(counter()?.classList.contains('field__counter--over')).toBe(true)
    expect(field().getAttribute('aria-invalid')).toBe('true')

    await click(copyButton())
    expect(writeText).toHaveBeenCalledWith(long)

    await click(saveButton())
    expect(updateSummary).not.toHaveBeenCalled()

    await type(field(), 's'.repeat(10000))
    await click(saveButton())
    expect(updateSummary).toHaveBeenCalledWith(SUMMARY_ID, { text: 's'.repeat(10000) })
  })
})
