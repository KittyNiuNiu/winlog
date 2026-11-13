import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import {
  ENTRY_ID,
  addedTags,
  chip,
  dateInput,
  entryFrom,
  foldButton,
  formError,
  key,
  options,
  pressedChips,
  resultInput,
  save,
  saveButton,
  savedBand,
  storedEntry,
  tagInput,
  textArea,
  type,
} from '../test/entryForm.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    getEntry: vi.fn(),
    updateEntry: vi.fn(),
    listTags: vi.fn(),
    suggestCategoryAndTags: vi.fn(),
  }
})

const getEntry = vi.mocked(api.getEntry)
const updateEntry = vi.mocked(api.updateEntry)
const listTags = vi.mocked(api.listTags)
const suggest = vi.mocked(api.suggestCategoryAndTags)

const EDIT_PATH = `/entries/${ENTRY_ID}/edit`
const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'

async function renderEdit(path = EDIT_PATH) {
  const result = renderRoute(path)
  await act(async () => {})
  return result
}

beforeEach(() => {
  storeTestSession()
  listTags.mockResolvedValue({ tags: ['incident', 'Leadership', 'Python'] })
  getEntry.mockResolvedValue(storedEntry())
  updateEntry.mockImplementation(async (id, body) => entryFrom(body, id))
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
})

describe('edit page (FR-E4)', () => {
  it('test_fr_e4_edit_page_fills_every_field_with_the_stored_entry', async () => {
    await renderEdit()

    expect(getEntry).toHaveBeenCalledWith(ENTRY_ID)
    expect(screen.getByRole('heading', { level: 1, name: 'Edit entry' })).toBeTruthy()
    expect(textArea().value).toBe('Led the incident review')
    expect(pressedChips()).toEqual(['Feedback'])
    // Its own date, not today.
    expect(dateInput().value).toBe('2026-10-05')
    // Open, because the entry has tags and a result.
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(addedTags()).toEqual(['Leadership', 'incident'])
    expect(resultInput().value).toBe('Fewer pages at night')
  })

  it('test_fr_e4_edit_page_order_has_cancel_and_no_just_saved', async () => {
    await renderEdit()

    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel.className).toContain('button--secondary')
    expect(saveButton().compareDocumentPosition(cancel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(textArea().compareDocumentPosition(dateInput()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(dateInput().compareDocumentPosition(foldButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(foldButton().compareDocumentPosition(saveButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Just saved' })).toBeNull()
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
  })

  it.each(['phone', 'laptop'] as const)('test_entries_is_current_on_the_edit_page_on_the_%s', async (width) => {
    setViewport(width)
    await renderEdit()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Entries' }).getAttribute('aria-current')).toBe('page')
  })

  it.each([
    ['tags', { tags: ['Leadership'], result_impact: null }, 'true'],
    ['a result', { tags: [], result_impact: 'Shipped' }, 'true'],
    ['neither', { tags: [], result_impact: null }, 'false'],
  ])('test_fr_e4_fold_on_an_entry_with_%s', async (_case, overrides, expanded) => {
    getEntry.mockResolvedValue(storedEntry(overrides))
    await renderEdit()

    expect(foldButton().getAttribute('aria-expanded')).toBe(expanded)
  })

  it('test_fr_e4_saving_replaces_the_whole_entry', async () => {
    await renderEdit()
    type(textArea(), 'Led the incident review and the follow-up')
    fireEvent.click(chip('Achievement'))
    type(dateInput(), '2026-10-06')
    fireEvent.click(screen.getByRole('button', { name: 'Remove incident' }))
    type(tagInput(), 'pyth')
    expect(options()).toEqual(['Python'])
    key(tagInput(), 'ArrowDown')
    key(tagInput(), 'Enter')
    type(resultInput(), '')

    await save()

    expect(updateEntry).toHaveBeenCalledTimes(1)
    expect(updateEntry).toHaveBeenCalledWith(ENTRY_ID, {
      text: 'Led the incident review and the follow-up',
      date: '2026-10-06',
      category: 'Achievement',
      tags: ['Leadership', 'Python'],
      result_impact: '',
    })
    expect(suggest).not.toHaveBeenCalled()
  })

  it('test_fr_e4_after_saving_entries_shows_the_saved_message_once', async () => {
    const { router } = await renderEdit()
    type(textArea(), 'Edited')

    await save()

    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
    expect(savedBand()).toBe('Entry saved.')
    const band = document.querySelector('.saved-region') as HTMLElement
    expect(band.compareDocumentPosition(screen.getByRole('heading', { level: 1 })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // No discard prompt right after saving.
    expect(screen.queryByRole('dialog')).toBeNull()
    // The history entry no longer carries it, so a reload does not show it again.
    expect(router.state.location.state).toBeNull()

    // Coming back later does not show it again.
    await act(async () => {
      await router.navigate('/review')
    })
    await act(async () => {
      await router.navigate('/')
    })
    expect(savedBand()).toBe('')
  })

  it('test_fr_e4_reloading_entries_after_a_save_does_not_show_the_message', async () => {
    renderRoute('/')
    await act(async () => {})

    expect(savedBand()).toBe('')
  })

  it('test_fr_e4_entry_deleted_while_editing_keeps_the_input', async () => {
    updateEntry.mockRejectedValue(new api.NotFoundError('Not found.', 404))
    const { router } = await renderEdit()
    type(textArea(), 'My changes')

    await save()

    expect(formError()).toBe("This entry no longer exists, so it can't be saved.")
    expect(router.state.location.pathname).toBe(EDIT_PATH)
    expect(textArea().value).toBe('My changes')
    expect(saveButton().disabled).toBe(false)
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_e4_%s_while_saving_keeps_the_input', async (_case, error, message) => {
    updateEntry.mockRejectedValue(error)
    await renderEdit()
    type(textArea(), 'My changes')

    await save()

    expect(formError()).toBe(message)
    expect(textArea().value).toBe('My changes')
  })

  it('test_fr_e4_cancel_without_changes_goes_to_entries_without_saving', async () => {
    const { router } = await renderEdit()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    })

    expect(router.state.location.pathname).toBe('/')
    expect(updateEntry).not.toHaveBeenCalled()
    expect(savedBand()).toBe('')
  })

  it('test_fr_e4_save_entry_layout_on_both_widths', async () => {
    await renderEdit()
    expect(saveButton().className).toContain('button--large')

    setViewport('laptop')
    expect(saveButton().className).not.toContain('button--large')
  })
})

describe('loading the entry (FR-E4, §12)', () => {
  it('test_fr_e4_loading_shows_progress_then_the_waking_up_hint', async () => {
    vi.useFakeTimers()
    let finish: () => void = () => {}
    getEntry.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => resolve(storedEntry())
        }),
    )
    await renderEdit()

    expect(screen.getByRole('heading', { level: 1, name: 'Edit entry' })).toBeTruthy()
    expect(screen.getByText('Loading entry…').getAttribute('role')).toBe('status')
    expect(screen.queryByLabelText('What happened?')).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()

    await act(async () => {
      finish()
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    expect(textArea().value).toBe('Led the incident review')
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_e4_a_load_error_shows_a_message_and_try_again_retries (%s)', async (_case, error, message) => {
    getEntry.mockRejectedValueOnce(error)
    await renderEdit()

    expect(screen.getByRole('alert').textContent).toBe(message)
    expect(screen.queryByLabelText('What happened?')).toBeNull()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    })

    expect(getEntry).toHaveBeenCalledTimes(2)
    expect(textArea().value).toBe('Led the incident review')
  })

  it.each([
    ['does not exist or belongs to another user', new api.NotFoundError('Not found.', 404)],
    [
      'has an invalid id',
      new api.ValidationError('The request has invalid fields.', 422, [
        { field: 'entryId', reason: 'Input should be a valid UUID' },
      ]),
    ],
  ])('test_fr_e4_an_entry_that_%s_shows_that_it_does_not_exist', async (_case, error) => {
    getEntry.mockRejectedValue(error)
    await renderEdit('/entries/not-a-uuid/edit')

    const status = screen.getByText("This entry doesn't exist.", { exact: false })
    expect(status.textContent).toBe("This entry doesn't exist. Back to entries")
    expect(within(status).getByRole('link', { name: 'Back to entries' }).getAttribute('href')).toBe('/')
    expect(screen.queryByLabelText('What happened?')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })
})

// Keyboard focus on the edit page (#84): it starts in the text field, a failed retry
// focuses the new "Try again", and neither takes focus from a control the user moved to.
describe('keyboard focus on the edit page (FR-E4, #84)', () => {
  function tryAgainButton(): HTMLButtonElement {
    return screen.getByRole('button', { name: 'Try again' }) as HTMLButtonElement
  }

  function entriesLink(): HTMLElement {
    return within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Entries' })
  }

  /** Focuses "Try again" and presses it, as a keyboard user does. */
  async function pressTryAgain() {
    tryAgainButton().focus()
    await act(async () => {
      fireEvent.click(tryAgainButton())
    })
  }

  function pendingEntry() {
    let resolve: (entry: api.Entry) => void = () => {}
    let reject: (error: unknown) => void = () => {}
    getEntry.mockImplementationOnce(
      () =>
        new Promise((res, rej) => {
          resolve = res
          reject = rej
        }),
    )
    return {
      resolve: async (entry: api.Entry) => act(async () => resolve(entry)),
      reject: async (error: unknown) => act(async () => reject(error)),
    }
  }

  it('test_fr_e4_edit_page_starts_in_text_field', async () => {
    await renderEdit()

    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e4_edit_page_starts_in_text_field_after_a_successful_retry', async () => {
    getEntry.mockRejectedValueOnce(new api.NetworkError())
    await renderEdit()

    await pressTryAgain()

    expect(textArea().value).toBe('Led the incident review')
    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e4_edit_page_keeps_focus_where_the_user_moved_while_loading', async () => {
    const load = pendingEntry()
    await renderEdit()
    entriesLink().focus()

    await load.resolve(storedEntry())

    expect(textArea().value).toBe('Led the incident review')
    expect(document.activeElement).toBe(entriesLink())
  })

  it('test_fr_e4_edit_page_keeps_focus_where_the_user_moved_while_retrying', async () => {
    getEntry.mockRejectedValueOnce(new api.NetworkError())
    await renderEdit()
    const retry = pendingEntry()
    await pressTryAgain()
    entriesLink().focus()

    await retry.resolve(storedEntry())

    expect(document.activeElement).toBe(entriesLink())
  })

  it('test_fr_e4_failed_retry_moves_focus_to_the_new_try_again', async () => {
    getEntry.mockRejectedValueOnce(new api.NetworkError())
    await renderEdit()
    // The first failure moves no focus.
    expect(document.activeElement).toBe(document.body)
    const first = tryAgainButton()
    const retry = pendingEntry()

    await pressTryAgain()
    // While the retry loads, the loading line shows and the old button is gone.
    expect(screen.getByText('Loading entry…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    await retry.reject(new api.NetworkError())

    expect(tryAgainButton()).not.toBe(first)
    expect(document.activeElement).toBe(tryAgainButton())
  })

  it('test_fr_e4_failed_retry_keeps_focus_where_the_user_moved', async () => {
    getEntry.mockRejectedValueOnce(new api.NetworkError())
    await renderEdit()
    const retry = pendingEntry()
    await pressTryAgain()
    entriesLink().focus()

    await retry.reject(new api.NetworkError())

    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
    expect(document.activeElement).toBe(entriesLink())
  })

  it('test_fr_e4_missing_entry_moves_no_focus', async () => {
    getEntry.mockRejectedValue(new api.NotFoundError('Not found.', 404))
    await renderEdit()

    expect(screen.getByText("This entry doesn't exist.", { exact: false })).toBeTruthy()
    expect(document.activeElement).toBe(document.body)
  })

  it.each([
    ['the entry was deleted', new api.NotFoundError('Not found.', 404)],
    ['a network error', new api.NetworkError()],
  ])('test_fr_e4_busy_save_keeps_focus_and_after_%s_focus_stays', async (_case, error) => {
    let fail: () => void = () => {}
    updateEntry.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(error)
        }),
    )
    await renderEdit()
    saveButton().focus()

    await save()
    expect(saveButton().textContent).toBe('Saving…')
    // Focusable while busy: a natively disabled button would drop focus in a browser.
    expect(saveButton().disabled).toBe(false)
    expect(document.activeElement).toBe(saveButton())
    await act(async () => {
      fail()
    })

    expect(formError()).not.toBe('')
    expect(document.activeElement).toBe(saveButton())
  })
})
