import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import type { Entry } from '../api/index.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { SAVED_MESSAGE_MS } from '../components/useSavedMessage.ts'
import { entrySavedState } from '../entries/entrySavedNotice.ts'
import { routes } from '../routes.tsx'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    listEntries: vi.fn(),
    deleteEntry: vi.fn(),
    getEntry: vi.fn(),
    listTags: vi.fn(),
  }
})

const listEntries = vi.mocked(api.listEntries)
const deleteEntry = vi.mocked(api.deleteEntry)
const getEntry = vi.mocked(api.getEntry)
const listTags = vi.mocked(api.listTags)

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const EMPTY_TEXT = 'No entries yet. Write your first win.'

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

// In the API's order: newest date first, then newest created first. The first entry is
// dated in the future (today is 2026-11-12 in these fixtures' world).
function sampleEntries(): Entry[] {
  return [
    makeEntry('future', '2027-01-05', { category: 'Learning', text: 'Plan the Q1 roadmap workshop.' }),
    makeEntry('dec31', '2026-12-31', { category: 'Side project' }),
    makeEntry('nov10b', '2026-11-10', {
      text: 'Led the incident review.\nWrote the timeline.',
      result_impact: 'Two of three follow-ups done in a week.',
      tags: ['incident', 'Leadership', 'Python'],
      created_at: '2026-11-10T15:00:00Z',
    }),
    makeEntry('nov10a', '2026-11-10', { category: 'Feedback', created_at: '2026-11-10T08:00:00Z' }),
    makeEntry('nov1', '2026-11-01'),
    makeEntry('nov2025', '2025-11-20', { category: 'Learning' }),
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

async function renderEntries(path = '/') {
  const result = renderRoute(path)
  await act(async () => {})
  return result
}

/** Renders `/` as after saving an edit (#27). */
async function renderAfterSave() {
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname: '/', state: entrySavedState() }] })
  connectLoginRedirect(router)
  render(<RouterProvider router={router} />)
  await act(async () => {})
  return { router }
}

function content(): HTMLElement {
  return document.querySelector('.entries-page__content') as HTMLElement
}

function monthHeadings(): string[] {
  return within(content())
    .queryAllByRole('heading', { level: 2 })
    .map((heading) => heading.textContent ?? '')
}

function rows(): HTMLElement[] {
  return Array.from(content().querySelectorAll<HTMLElement>('.entry-row'))
}

function rowTexts(): string[] {
  return rows().map((row) => row.querySelector('.entry-row__text')?.textContent ?? '')
}

/** The month section the row with this text is in. */
function monthOf(text: string): string {
  const section = screen.getByText(text).closest('section') as HTMLElement
  return within(section).getByRole('heading', { level: 2 }).textContent ?? ''
}

function deleteButton(date: string): HTMLButtonElement {
  return screen.getByRole('button', { name: `Delete entry from ${date}` }) as HTMLButtonElement
}

function editLink(date: string): HTMLAnchorElement {
  return screen.getByRole('link', { name: `Edit entry from ${date}` }) as HTMLAnchorElement
}

function dialog(): HTMLDialogElement | null {
  const element = document.querySelector('dialog')
  return element instanceof HTMLDialogElement && element.open ? element : null
}

function openDialog(): HTMLDialogElement {
  const element = dialog()
  if (element === null) {
    throw new Error('the "Delete this entry?" dialog is not open')
  }
  return element
}

function dialogButton(name: string | RegExp): HTMLButtonElement {
  return within(openDialog()).getByRole('button', { name }) as HTMLButtonElement
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element)
  })
}

async function deleteRow(date: string): Promise<void> {
  await click(deleteButton(date))
  await click(dialogButton('Delete entry'))
}

/** The visible saved band's text, or ''. */
function savedBand(): string {
  return document.querySelector('.saved-message')?.textContent ?? ''
}

/** The information message in the message slot, or ''. */
function notice(): string {
  return document.querySelector('.entries-page__notice')?.textContent ?? ''
}

function primaryButtons(): Element[] {
  return Array.from(document.querySelectorAll('.button--primary'))
}

/** The "New entry" link in the page content (not the laptop sidebar's). */
function pageNewEntryLinks(): HTMLElement[] {
  const main = document.getElementById('main') as HTMLElement
  return within(main).queryAllByRole('link', { name: 'New entry' })
}

beforeEach(() => {
  storeTestSession()
  listEntries.mockResolvedValue({ entries: sampleEntries() })
  deleteEntry.mockResolvedValue(undefined)
  listTags.mockResolvedValue({ tags: [] })
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('the entries page (FR-E4)', () => {
  it('test_fr_e4_page_is_titled_entries_and_entries_is_current', async () => {
    await renderEntries()

    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Entries' }).getAttribute('aria-current')).toBe('page')
  })

  it('test_fr_e4_list_loads_once_without_filters_and_keeps_the_api_order', async () => {
    // Not sorted by any rule the page could apply: the page must keep this order.
    const entries = [
      makeEntry('b', '2026-11-10', { text: 'Created later', created_at: '2026-11-10T18:00:00Z' }),
      makeEntry('a', '2026-11-10', { text: 'Created earlier', created_at: '2026-11-10T07:00:00Z' }),
      makeEntry('c', '2026-11-03', { text: 'Older' }),
    ]
    listEntries.mockResolvedValue({ entries })

    await renderEntries()

    expect(listEntries).toHaveBeenCalledTimes(1)
    expect(listEntries.mock.calls[0]).toEqual([])
    expect(rowTexts()).toEqual(['Created later', 'Created earlier', 'Older'])
  })

  it('test_fr_e4_entries_are_grouped_by_month_newest_first', async () => {
    await renderEntries()

    expect(monthHeadings()).toEqual(['January 2027', 'December 2026', 'November 2026', 'November 2025'])
    // Each month is a section named by its heading, with its rows in a list.
    const sections = content().querySelectorAll('section')
    expect(sections).toHaveLength(4)
    const november = within(content()).getByRole('region', { name: 'November 2026' })
    expect(november.querySelectorAll(':scope > ul > li > .entry-row')).toHaveLength(3)
  })

  it('test_fr_e4_same_month_in_another_year_is_a_separate_group', async () => {
    await renderEntries()

    expect(monthOf('Entry nov1')).toBe('November 2026')
    expect(monthOf('Entry nov2025')).toBe('November 2025')
  })

  it('test_fr_e4_future_dated_entry_shows_in_its_own_month_at_the_top', async () => {
    await renderEntries()

    expect(monthHeadings()[0]).toBe('January 2027')
    expect(rowTexts()[0]).toBe('Plan the Q1 roadmap workshop.')
    expect(monthOf('Plan the Q1 roadmap workshop.')).toBe('January 2027')
  })

  it('test_fr_e4_row_shows_date_category_text_result_and_tags', async () => {
    await renderEntries()

    const row = rows()[2]
    const date = within(row).getByText('10 Nov')
    expect(date.tagName).toBe('TIME')
    expect(date.getAttribute('datetime')).toBe('2026-11-10')
    expect(within(row).getByText('Achievement').classList.contains('category-label')).toBe(true)
    expect(row.querySelector('.entry-row__text')?.textContent).toBe('Led the incident review.\nWrote the timeline.')
    expect(row.querySelector('.entry-row__result')?.textContent).toBe('Result: Two of three follow-ups done in a week.')
    const tags = within(row).getByRole('list', { name: 'Tags' })
    expect(within(tags).getAllByRole('listitem').map((tag) => tag.textContent)).toEqual([
      'incident',
      'Leadership',
      'Python',
    ])
    // Read-only: no remove buttons in the tags.
    expect(within(tags).queryAllByRole('button')).toEqual([])
  })

  it('test_fr_e4_row_without_result_or_tags_has_no_result_line_and_no_tag_area', async () => {
    await renderEntries()

    const row = rows()[3]
    expect(within(row).getByText('Feedback')).toBeTruthy()
    expect(within(row).queryByText(/Result/)).toBeNull()
    expect(within(row).queryByRole('list', { name: 'Tags' })).toBeNull()
    expect(row.querySelector('.entry-row__tags')).toBeNull()
  })

  it('test_fr_e4_dates_and_headings_come_from_the_stored_text', async () => {
    await renderEntries()

    expect(within(rows()[4]).getByText('1 Nov')).toBeTruthy()
    expect(monthOf('Entry nov1')).toBe('November 2026')
    expect(within(rows()[1]).getByText('31 Dec')).toBeTruthy()
    expect(monthOf('Entry dec31')).toBe('December 2026')
  })

  it('test_fr_e4_dates_and_headings_do_not_shift_in_a_time_zone_behind_utc', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    // There, new Date('2026-11-01') is still 31 October.
    expect(new Date('2026-11-01').getDate()).toBe(31)

    await renderEntries()

    expect(within(rows()[4]).getByText('1 Nov')).toBeTruthy()
    expect(monthOf('Entry nov1')).toBe('November 2026')
    expect(screen.queryByText('October 2026')).toBeNull()
    expect(within(rows()[1]).getByText('31 Dec')).toBeTruthy()
    expect(monthOf('Entry dec31')).toBe('December 2026')
    expect(editLink('1 Nov 2026')).toBeTruthy()
  })

  it('test_fr_e4_month_names_are_english_in_any_browser_language', async () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE')
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-DE'])

    await renderEntries()

    expect(monthHeadings()).toEqual(['January 2027', 'December 2026', 'November 2026', 'November 2025'])
    expect(within(rows()[1]).getByText('31 Dec')).toBeTruthy()
  })

  it('test_fr_e4_edit_and_delete_have_names_with_the_full_date', async () => {
    await renderEntries()

    for (const row of rows()) {
      expect(within(row).getAllByRole('link')).toHaveLength(1)
      expect(within(row).getAllByRole('button')).toHaveLength(1)
    }
    const edit = editLink('1 Nov 2026')
    expect(edit.getAttribute('href')).toBe('/entries/nov1/edit')
    expect(deleteButton('1 Nov 2026').getAttribute('type')).toBe('button')
    expect(editLink('31 Dec 2026').getAttribute('href')).toBe('/entries/dec31/edit')
    expect(editLink('5 Jan 2027').getAttribute('href')).toBe('/entries/future/edit')
    expect(screen.getAllByRole('link', { name: 'Edit entry from 10 Nov 2026' })).toHaveLength(2)
    // Each has its icon, hidden from screen readers.
    expect(edit.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    expect(deleteButton('1 Nov 2026').querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('test_fr_e4_edit_opens_the_edit_page', async () => {
    getEntry.mockReturnValue(new Promise(() => {}))
    const { router } = await renderEntries()

    await click(editLink('1 Nov 2026'))

    expect(router.state.location.pathname).toBe('/entries/nov1/edit')
    expect(screen.getByRole('heading', { level: 1, name: 'Edit entry' })).toBeTruthy()
  })
})

describe('the "New entry" button and the One Action Rule', () => {
  it('test_fr_e4_phone_has_a_new_entry_button_under_the_title', async () => {
    await renderEntries()

    const links = pageNewEntryLinks()
    expect(links).toHaveLength(1)
    const [link] = links
    expect(link.getAttribute('href')).toBe('/entries/new')
    expect(link.classList.contains('button--primary')).toBe(true)
    // Directly under the title, above the list.
    const title = screen.getByRole('heading', { level: 1, name: 'Entries' })
    expect(title.nextElementSibling?.contains(link)).toBe(true)
    expect(link.compareDocumentPosition(content()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('test_fr_e4_laptop_has_no_second_new_entry_button', async () => {
    setViewport('laptop')
    await renderEntries()

    expect(pageNewEntryLinks()).toEqual([])
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'New entry' }).classList.contains('button--secondary')).toBe(true)
    expect(primaryButtons()).toEqual([])
  })

  it('test_fr_e4_new_entry_button_opens_the_capture_screen', async () => {
    const { router } = await renderEntries()

    await click(pageNewEntryLinks()[0])

    expect(router.state.location.pathname).toBe('/entries/new')
  })

  it.each(['phone', 'laptop'] as const)('test_fr_e4_at_most_one_plum_fill_in_every_state_%s', async (width) => {
    setViewport(width)
    const atMostOne = () => expect(primaryButtons().length).toBeLessThanOrEqual(1)

    // Loading.
    const load = deferred<{ entries: Entry[] }>()
    listEntries.mockReturnValueOnce(load.promise)
    const first = await renderEntries()
    atMostOne()
    first.unmount()

    // Load failed.
    listEntries.mockRejectedValueOnce(new api.NetworkError())
    const second = await renderEntries()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
    atMostOne()
    second.unmount()

    // Empty.
    listEntries.mockResolvedValueOnce({ entries: [] })
    const third = await renderEntries()
    expect(screen.getByText(EMPTY_TEXT)).toBeTruthy()
    expect(primaryButtons()).toHaveLength(1)
    third.unmount()

    // List, with the dialog open, with a message, and with the dialog's busy state.
    await renderEntries()
    atMostOne()
    await click(deleteButton('1 Nov 2026'))
    atMostOne()
    const pending = deferred<undefined>()
    deleteEntry.mockReturnValueOnce(pending.promise)
    await click(dialogButton('Delete entry'))
    expect(dialogButton('Deleting…').classList.contains('button--secondary')).toBe(true)
    atMostOne()
    await act(async () => {
      pending.resolve(undefined)
    })
    expect(savedBand()).toBe('Entry deleted.')
    atMostOne()
    deleteEntry.mockRejectedValueOnce(new api.NotFoundError('Not found.', 404))
    await deleteRow('31 Dec 2026')
    expect(notice()).toBe('This entry was already deleted.')
    atMostOne()
  })
})

describe('deleting an entry (FR-E4)', () => {
  it('test_fr_e4_delete_asks_for_confirmation', async () => {
    await renderEntries()
    expect(dialog()).toBeNull()

    await click(deleteButton('1 Nov 2026'))

    const element = openDialog()
    expect(within(element).getByRole('heading', { level: 2 }).textContent).toBe('Delete this entry?')
    expect(document.getElementById(element.getAttribute('aria-labelledby') ?? '')?.textContent).toBe(
      'Delete this entry?',
    )
    expect(document.getElementById(element.getAttribute('aria-describedby') ?? '')?.textContent).toBe(
      "This can't be undone.",
    )
    const buttons = within(element).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Cancel', 'Delete entry'])
    for (const button of buttons) {
      expect(button.classList.contains('button--secondary')).toBe(true)
    }
    expect(document.activeElement).toBe(dialogButton('Cancel'))
    expect(deleteEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e4_cancel_keeps_entry', async () => {
    await renderEntries()
    await click(deleteButton('1 Nov 2026'))

    await click(dialogButton('Cancel'))

    expect(dialog()).toBeNull()
    expect(deleteEntry).not.toHaveBeenCalled()
    expect(rowTexts()).toContain('Entry nov1')
    expect(document.activeElement).toBe(deleteButton('1 Nov 2026'))
  })

  it('test_fr_e4_escape_keeps_entry', async () => {
    await renderEntries()
    await click(deleteButton('1 Nov 2026'))

    await act(async () => {
      fireEvent.keyDown(openDialog(), { key: 'Escape' })
    })

    expect(dialog()).toBeNull()
    expect(deleteEntry).not.toHaveBeenCalled()
    expect(rowTexts()).toContain('Entry nov1')
    expect(document.activeElement).toBe(deleteButton('1 Nov 2026'))
  })

  it("test_fr_e4_browser_close_request_keeps_entry", async () => {
    await renderEntries()
    await click(deleteButton('1 Nov 2026'))

    await act(async () => {
      openDialog().dispatchEvent(new Event('cancel', { cancelable: true }))
    })

    expect(dialog()).toBeNull()
    expect(deleteEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e4_double_tap_sends_one_request_and_nothing_else_works_while_deleting', async () => {
    const pending = deferred<undefined>()
    deleteEntry.mockReturnValue(pending.promise)
    await renderEntries()
    await click(deleteButton('1 Nov 2026'))

    await act(async () => {
      fireEvent.click(dialogButton('Delete entry'))
      fireEvent.click(dialogButton(/^(Delete entry|Deleting…)$/))
    })

    expect(deleteEntry).toHaveBeenCalledTimes(1)
    expect(deleteEntry).toHaveBeenCalledWith('nov1')
    const busy = dialogButton('Deleting…')
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(busy.disabled).toBe(true)
    expect(busy.querySelector('.spinner')).not.toBeNull()
    // Cancel and Escape do nothing while it runs.
    await click(dialogButton('Cancel'))
    await act(async () => {
      fireEvent.keyDown(openDialog(), { key: 'Escape' })
      openDialog().dispatchEvent(new Event('cancel', { cancelable: true }))
    })
    expect(dialog()).not.toBeNull()
    expect(rowTexts()).toContain('Entry nov1')

    await act(async () => {
      pending.resolve(undefined)
    })
    expect(dialog()).toBeNull()
    expect(deleteEntry).toHaveBeenCalledTimes(1)
  })

  it('test_fr_e4_delete_removes_the_row_and_shows_entry_deleted', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    await renderEntries()

    await deleteRow('1 Nov 2026')

    expect(deleteEntry).toHaveBeenCalledWith('nov1')
    expect(dialog()).toBeNull()
    expect(rowTexts()).not.toContain('Entry nov1')
    expect(rows()).toHaveLength(5)
    // Not loaded again.
    expect(listEntries).toHaveBeenCalledTimes(1)
    const status = document.querySelector('.saved-region') as HTMLElement
    expect(status.getAttribute('role')).toBe('status')
    expect(status.textContent).toBe('Entry deleted.')
    expect(status.querySelector('svg')).not.toBeNull()
    expect(notice()).toBe('')
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('test_fr_e4_entry_deleted_goes_after_its_time', async () => {
    vi.useFakeTimers()
    await renderEntries()
    await deleteRow('1 Nov 2026')
    expect(savedBand()).toBe('Entry deleted.')

    act(() => {
      vi.advanceTimersByTime(SAVED_MESSAGE_MS)
    })

    expect(savedBand()).toBe('')
  })

  it('test_fr_e4_already_deleted_removes_the_row_and_shows_information', async () => {
    deleteEntry.mockRejectedValue(new api.NotFoundError('Not found.', 404))
    await renderEntries()

    await deleteRow('1 Nov 2026')

    expect(dialog()).toBeNull()
    expect(rowTexts()).not.toContain('Entry nov1')
    const message = document.querySelector('.entries-page__notice') as HTMLElement
    expect(message.textContent).toBe('This entry was already deleted.')
    expect(message.getAttribute('role')).toBe('status')
    expect(message.classList.contains('message--info')).toBe(true)
    expect(savedBand()).toBe('')
    expect(listEntries).toHaveBeenCalledTimes(1)
  })

  it('test_fr_e4_already_deleted_stays_until_replaced', async () => {
    vi.useFakeTimers()
    deleteEntry.mockRejectedValueOnce(new api.NotFoundError('Not found.', 404))
    await renderEntries()
    await deleteRow('1 Nov 2026')

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(notice()).toBe('This entry was already deleted.')

    await deleteRow('31 Dec 2026')
    expect(notice()).toBe('')
    expect(savedBand()).toBe('Entry deleted.')
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_e4_delete_with_%s_keeps_the_dialog_and_the_row', async (_label, error, text) => {
    deleteEntry.mockRejectedValueOnce(error)
    await renderEntries()

    await deleteRow('1 Nov 2026')

    const element = openDialog()
    expect(within(element).getByRole('alert').textContent).toBe(text)
    expect(rowTexts()).toContain('Entry nov1')
    expect(savedBand()).toBe('')
    const retry = dialogButton('Delete entry')
    expect(retry.disabled).toBe(false)
    expect(document.activeElement).toBe(retry)

    // Pressing it again tries again.
    await click(retry)
    expect(deleteEntry).toHaveBeenCalledTimes(2)
    expect(dialog()).toBeNull()
    expect(rowTexts()).not.toContain('Entry nov1')
    expect(savedBand()).toBe('Entry deleted.')
  })

  it('test_fr_e4_cancel_after_a_failed_delete_keeps_entry', async () => {
    deleteEntry.mockRejectedValueOnce(new api.UnknownError('Internal error.', 500, 'internal_error'))
    await renderEntries()
    await deleteRow('1 Nov 2026')

    await click(dialogButton('Cancel'))

    expect(dialog()).toBeNull()
    expect(rowTexts()).toContain('Entry nov1')
    expect(document.activeElement).toBe(deleteButton('1 Nov 2026'))

    // The next dialog starts without the old error.
    await click(deleteButton('1 Nov 2026'))
    expect(within(openDialog()).getByRole('alert').textContent).toBe('')
  })

  it('test_fr_e4_expired_login_during_delete_opens_the_login_page', async () => {
    const actual = await vi.importActual<typeof import('../api/index.ts')>('../api/index.ts')
    deleteEntry.mockImplementation(actual.deleteEntry)
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test')
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ code: 'not_authenticated', message: 'Log in again.' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    const { router } = await renderEntries()

    await deleteRow('1 Nov 2026')

    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
  })

  it('test_fr_e4_month_heading_goes_with_its_last_entry', async () => {
    await renderEntries()

    await deleteRow('31 Dec 2026')

    expect(monthHeadings()).toEqual(['January 2027', 'November 2026', 'November 2025'])
  })

  it('test_fr_e4_empty_state_after_deleting_the_last_entry', async () => {
    listEntries.mockResolvedValue({ entries: [makeEntry('only', '2026-11-10')] })
    await renderEntries()

    await deleteRow('10 Nov 2026')

    expect(monthHeadings()).toEqual([])
    expect(rows()).toEqual([])
    expect(screen.getByText(EMPTY_TEXT)).toBeTruthy()
    expect(savedBand()).toBe('Entry deleted.')
    // One way in: the empty state's button, not the one under the title.
    const links = pageNewEntryLinks()
    expect(links).toHaveLength(1)
    expect(links[0].closest('.empty-state')).not.toBeNull()
    expect(document.activeElement).toBe(links[0])
  })

  it('test_fr_e4_focus_moves_to_the_row_that_takes_the_place', async () => {
    await renderEntries()

    // The last November 2026 row: the next row is in November 2025.
    await deleteRow('1 Nov 2026')
    expect(document.activeElement).toBe(editLink('20 Nov 2025'))

    // A row in the middle of a month.
    await click(screen.getAllByRole('button', { name: 'Delete entry from 10 Nov 2026' })[0])
    await click(dialogButton('Delete entry'))
    expect(rowTexts()).not.toContain('Led the incident review.\nWrote the timeline.')
    expect(document.activeElement).toBe(editLink('10 Nov 2026'))
    expect(document.activeElement?.closest('.entry-row')?.textContent).toContain('Entry nov10a')
  })

  it('test_fr_e4_focus_moves_to_the_row_above_after_deleting_the_last_row', async () => {
    await renderEntries()

    await deleteRow('20 Nov 2025')

    expect(document.activeElement).toBe(editLink('1 Nov 2026'))
    expect(document.activeElement).not.toBe(document.body)
  })

  it('test_fr_e4_focus_after_already_deleted_moves_to_the_next_row', async () => {
    deleteEntry.mockRejectedValue(new api.NotFoundError('Not found.', 404))
    await renderEntries()

    await deleteRow('5 Jan 2027')

    expect(document.activeElement).toBe(editLink('31 Dec 2026'))
  })
})

describe('messages at the top', () => {
  it('test_fr_e4_messages_sit_above_the_title_in_the_list_column', async () => {
    await renderAfterSave()

    const page = document.querySelector('.entries-page') as HTMLElement
    expect(page.classList.contains('page')).toBe(true)
    const title = screen.getByRole('heading', { level: 1, name: 'Entries' })
    const band = page.querySelector('.saved-region') as HTMLElement
    const information = page.querySelector('.entries-page__notice') as HTMLElement
    // Both slots are children of the same column as the list, before the title.
    expect(band.parentElement).toBe(page)
    expect(information.parentElement).toBe(page)
    expect(content().parentElement).toBe(page)
    expect(band.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(information.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('test_fr_e4_after_saving_an_edit_entry_saved_shows_once', async () => {
    const { router } = await renderAfterSave()

    expect(savedBand()).toBe('Entry saved.')
    // The state is forgotten, so a reload does not show it again.
    expect(router.state.location.state).toBeNull()

    await act(async () => {
      await router.navigate('/review')
    })
    await act(async () => {
      await router.navigate('/')
    })
    expect(savedBand()).toBe('')
  })

  it('test_fr_e4_one_message_at_a_time', async () => {
    deleteEntry.mockResolvedValueOnce(undefined)
    deleteEntry.mockRejectedValueOnce(new api.NotFoundError('Not found.', 404))
    deleteEntry.mockResolvedValueOnce(undefined)
    await renderAfterSave()
    expect(savedBand()).toBe('Entry saved.')

    // "Entry deleted." replaces "Entry saved.".
    await deleteRow('5 Jan 2027')
    expect(document.querySelectorAll('.saved-message')).toHaveLength(1)
    expect(savedBand()).toBe('Entry deleted.')
    expect(notice()).toBe('')

    // "This entry was already deleted." replaces "Entry deleted.".
    await deleteRow('31 Dec 2026')
    expect(savedBand()).toBe('')
    expect(notice()).toBe('This entry was already deleted.')

    // And "Entry deleted." replaces it.
    await deleteRow('1 Nov 2026')
    expect(notice()).toBe('')
    expect(savedBand()).toBe('Entry deleted.')
    // Both live regions stay in the page.
    expect(document.querySelectorAll('.entries-page > [role="status"]')).toHaveLength(2)
  })

  it('test_fr_e4_deleting_again_keeps_one_band_and_restarts_its_time', async () => {
    vi.useFakeTimers()
    await renderEntries()
    await deleteRow('5 Jan 2027')
    const band = document.querySelector('.saved-message')

    act(() => {
      vi.advanceTimersByTime(4_000)
    })
    await deleteRow('31 Dec 2026')

    expect(document.querySelectorAll('.saved-message')).toHaveLength(1)
    expect(document.querySelector('.saved-message')).toBe(band)
    act(() => {
      vi.advanceTimersByTime(4_000)
    })
    expect(savedBand()).toBe('Entry deleted.')
    act(() => {
      vi.advanceTimersByTime(SAVED_MESSAGE_MS - 4_000)
    })
    expect(savedBand()).toBe('')
  })
})

describe('empty, loading and error states', () => {
  it('test_fr_e4_empty_state_for_a_user_without_entries', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    await renderEntries()

    expect(screen.getByText(EMPTY_TEXT)).toBeTruthy()
    const links = pageNewEntryLinks()
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('href')).toBe('/entries/new')
    expect(links[0].classList.contains('button--primary')).toBe(true)
    expect(links[0].closest('.empty-state')).not.toBeNull()
    expect(monthHeadings()).toEqual([])
    expect(document.querySelector('.empty-state__illustration')).toBeNull()
  })

  it('test_fr_e4_empty_state_button_opens_the_capture_screen', async () => {
    listEntries.mockResolvedValue({ entries: [] })
    const { router } = await renderEntries()

    await click(pageNewEntryLinks()[0])

    expect(router.state.location.pathname).toBe('/entries/new')
  })

  it('test_fr_e4_loading_shows_progress_then_the_waking_up_hint', async () => {
    vi.useFakeTimers()
    listEntries.mockReturnValue(new Promise(() => {}))
    await renderEntries()

    const status = screen.getByText('Loading entries…')
    expect(status.getAttribute('role')).toBe('status')
    expect(status.querySelector('.spinner')).not.toBeNull()
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    expect(monthHeadings()).toEqual([])
    expect(screen.queryByText(EMPTY_TEXT)).toBeNull()
    // On the phone, "New entry" is there while loading.
    expect(pageNewEntryLinks()).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).getAttribute('role')).toBe('status')
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_e4_load_with_%s_shows_the_error_and_try_again', async (_label, error, text) => {
    listEntries.mockRejectedValueOnce(error)
    await renderEntries()

    expect(screen.getByRole('alert').textContent).toBe(text)
    expect(screen.queryByText(EMPTY_TEXT)).toBeNull()
    // On the phone, "New entry" is there after a load error.
    expect(pageNewEntryLinks()).toHaveLength(1)
    const retry = screen.getByRole('button', { name: 'Try again' })
    expect(retry.classList.contains('button--secondary')).toBe(true)

    const load = deferred<{ entries: Entry[] }>()
    listEntries.mockReturnValueOnce(load.promise)
    await click(retry)
    expect(screen.getByText('Loading entries…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()

    await act(async () => {
      load.resolve({ entries: sampleEntries() })
    })
    expect(listEntries).toHaveBeenCalledTimes(2)
    expect(rows()).toHaveLength(6)
  })
})
