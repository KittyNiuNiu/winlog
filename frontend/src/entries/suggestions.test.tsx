import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import type { Suggestion } from '../api/index.ts'
import {
  ENTRY_ID,
  addedTags,
  categoryGroup,
  dateInput,
  entryFrom,
  foldButton,
  formError,
  key,
  messagesOf,
  openFold,
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

// AI suggestions on the entry form (#28: FR-S1 to FR-S3, §7.3, §8). The API client is
// mocked: no test calls the AI.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    createEntry: vi.fn(),
    getEntry: vi.fn(),
    updateEntry: vi.fn(),
    listTags: vi.fn(),
    suggestCategoryAndTags: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const createEntry = vi.mocked(api.createEntry)
const getEntry = vi.mocked(api.getEntry)
const updateEntry = vi.mocked(api.updateEntry)
const listTags = vi.mocked(api.listTags)
const suggest = vi.mocked(api.suggestCategoryAndTags)

const EDIT_PATH = `/entries/${ENTRY_ID}/edit`
const UNAVAILABLE = "Suggestions aren't available right now. You can fill in the fields yourself."
const USER_LIMIT = "You've used today's suggestions. They're available again after midnight UTC."
const GLOBAL_LIMIT = "Winlog has reached today's AI limit for everyone. Try again after midnight UTC."
const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'

// --- Queries ---

function suggestButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Suggest category and tags|Suggesting…)$/ }) as HTMLButtonElement
}

function discardButton(): HTMLButtonElement | null {
  return screen.queryByRole('button', { name: 'Discard suggestions' }) as HTMLButtonElement | null
}

function hintButton(): HTMLButtonElement | null {
  return screen.queryByRole('button', { name: /^Suggested: / }) as HTMLButtonElement | null
}

/** A category chip by its category, whether or not it is marked "Suggested". */
function categoryChip(category: string): HTMLButtonElement {
  return within(categoryGroup()).getByRole('button', {
    name: new RegExp(`^${category}(, suggested)?$`),
  }) as HTMLButtonElement
}

/** The selected category, with ", suggested" when it carries the mark (its accessible name). */
function selected(): string[] {
  return within(categoryGroup())
    .queryAllByRole('button', { pressed: true })
    .map((button) => (button.className.includes('chip--suggested') ? `${label(button)}, suggested` : label(button)))
}

function label(chipButton: HTMLElement): string {
  return chipButton.querySelector('.chip__label')?.textContent ?? ''
}

/** The added tags as screen readers hear them: "<tag>" or "<tag>, suggested". */
function spokenTags(): string[] {
  const list = screen.queryByRole('list', { name: 'Added tags', hidden: true })
  if (list === null) {
    return []
  }
  return within(list)
    .getAllByRole('listitem', { hidden: true })
    .map((item) => {
      const copy = item.cloneNode(true) as HTMLElement
      copy.querySelectorAll('[aria-hidden="true"]').forEach((hidden) => hidden.remove())
      return copy.textContent ?? ''
    })
}

function notice(): string {
  return document.querySelector('.entry-form__notice')?.textContent ?? ''
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

/** Makes the next suggestion request wait until the test answers it. */
function pendingSuggestion() {
  const answer = deferred<Suggestion>()
  suggest.mockImplementationOnce(() => answer.promise)
  return {
    resolve: async (suggestion: Suggestion) => {
      await act(async () => {
        answer.resolve(suggestion)
      })
    },
    reject: async (error: unknown) => {
      await act(async () => {
        answer.reject(error)
      })
    },
  }
}

async function tapSuggest(): Promise<void> {
  await act(async () => {
    fireEvent.click(suggestButton())
  })
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element)
  })
}

async function renderAt(path: string) {
  const result = renderRoute(path)
  await act(async () => {})
  return result
}

function dialogOpen(): boolean {
  const element = document.querySelector('dialog')
  return element instanceof HTMLDialogElement && element.open
}

function navLink(name: string): HTMLElement {
  return within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name })
}

beforeEach(() => {
  storeTestSession()
  listTags.mockResolvedValue({ tags: ['Leadership', 'Python'] })
  createEntry.mockImplementation(async (body) => entryFrom(body))
  getEntry.mockResolvedValue(storedEntry())
  updateEntry.mockImplementation(async (id, body) => entryFrom(body, id))
  suggest.mockResolvedValue({ category: 'Learning', tags: ['Python', 'Mock tag'] })
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('the suggest button (FR-S1)', () => {
  it('test_fr_s1_button_sits_under_the_text_and_is_secondary_with_its_icon', async () => {
    await renderAt('/entries/new')

    const button = suggestButton()
    expect(button.textContent).toBe('Suggest category and tags')
    expect(button.className).toContain('button--secondary')
    expect(button.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    // Directly under the text field, above the category chips, and the order of #27 stays.
    const order = [textArea(), button, categoryGroup(), dateInput(), foldButton(), saveButton()]
    for (let index = 1; index < order.length; index += 1) {
      const before = order[index - 1] as Node
      expect(before.compareDocumentPosition(order[index] as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
  })

  it('test_fr_s1_button_is_on_the_edit_page_too', async () => {
    await renderAt(EDIT_PATH)

    expect(suggestButton().disabled).toBe(false)
    expect(textArea().compareDocumentPosition(suggestButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('test_fr_s1_button_is_disabled_while_the_text_is_empty_or_whitespace', async () => {
    await renderAt('/entries/new')
    expect(suggestButton().disabled).toBe(true)

    type(textArea(), '  \n\t ')
    expect(suggestButton().disabled).toBe(true)
    fireEvent.click(suggestButton())

    type(textArea(), 'Learned pytest fixtures')
    expect(suggestButton().disabled).toBe(false)
    expect(suggest).not.toHaveBeenCalled()
  })

  it('test_fr_s1_button_is_disabled_while_saving', async () => {
    const saving = deferred<api.Entry>()
    createEntry.mockImplementation(() => saving.promise)
    await renderAt('/entries/new')
    type(textArea(), 'Shipped the export')
    fireEvent.click(categoryChip('Achievement'))

    await save()

    expect(saveButton().textContent).toBe('Saving…')
    expect(suggestButton().disabled).toBe(true)
    expect(suggestButton().getAttribute('aria-busy')).toBe('false')
    fireEvent.click(suggestButton())
    expect(suggest).not.toHaveBeenCalled()
    await act(async () => {
      saving.resolve(entryFrom({ text: 'Shipped the export', date: '2026-11-12', category: 'Achievement' }))
    })
  })

  it('test_fr_s1_a_double_tap_sends_one_request_with_only_the_text', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), '  Learned how pytest fixtures work  ')
    fireEvent.click(categoryChip('Feedback'))
    openFold()
    type(tagInput(), 'mine,')

    await act(async () => {
      fireEvent.click(suggestButton())
      fireEvent.click(suggestButton())
    })
    await tapSuggest()

    expect(suggest).toHaveBeenCalledTimes(1)
    // Only the current text, as typed.
    expect(suggest).toHaveBeenCalledWith({ text: '  Learned how pytest fixtures work  ' })
    await answer.resolve({ category: 'Learning', tags: [] })
  })

  it('test_fr_s1_while_asking_the_button_shows_progress_and_the_form_stays_usable', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()

    const button = suggestButton()
    expect(button.textContent).toBe('Suggesting…')
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(button.getAttribute('aria-disabled')).toBe('true')
    expect(button.disabled).toBe(false)
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.className).toContain('button--secondary')
    expect(button.querySelector('.spinner')).not.toBeNull()
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
    // Everything else can still be used.
    type(textArea(), 'Learned about pytest fixtures')
    fireEvent.click(categoryChip('Achievement'))
    type(dateInput(), '2026-11-01')
    openFold()
    type(tagInput(), 'testing,')
    type(resultInput(), 'Faster tests')
    expect(textArea().value).toBe('Learned about pytest fixtures')
    expect(selected()).toEqual(['Achievement'])
    expect(dateInput().value).toBe('2026-11-01')
    expect(addedTags()).toEqual(['testing'])
    expect(resultInput().value).toBe('Faster tests')
    expect(saveButton().disabled).toBe(false)

    await answer.resolve({ category: 'Learning', tags: [] })
    expect(suggestButton().textContent).toBe('Suggest category and tags')
    expect(suggestButton().disabled).toBe(false)
  })

  it.each([
    ['a result', async (answer: ReturnType<typeof pendingSuggestion>) => answer.resolve({ category: 'Learning', tags: [] })],
    ['a notice', async (answer: ReturnType<typeof pendingSuggestion>) => answer.reject(new api.AiUnavailableError('x', 503))],
  ])('test_fr_s1_focus_is_back_on_the_button_after_%s', async (_case, finish) => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    suggestButton().focus()

    await tapSuggest()
    // The busy button keeps focus throughout (#84): it never drops to the page body.
    expect(suggestButton().textContent).toBe('Suggesting…')
    expect(document.activeElement).toBe(suggestButton())

    await finish(answer)

    expect(document.activeElement).toBe(suggestButton())
  })

  it('test_fr_s1_focus_stays_where_the_user_moved_it_while_asking', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    suggestButton().focus()

    await tapSuggest()
    dateInput().focus()
    await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })

    expect(document.activeElement).toBe(dateInput())
  })
})

describe('category (FR-S2: fill only what is empty)', () => {
  it('test_fr_s2_an_empty_category_is_filled_and_marked_suggested', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()

    const chipButton = within(categoryGroup()).getByRole('button', { name: 'Learning, suggested', pressed: true })
    expect(chipButton.className).toContain('chip--suggested')
    // The visible mark, hidden from screen readers (they hear ", suggested").
    const mark = chipButton.querySelector('.chip__mark') as HTMLElement
    expect(mark.textContent).toBe('Suggested')
    expect(mark.getAttribute('aria-hidden')).toBe('true')
    expect(mark.querySelector('svg')).not.toBeNull()
    expect(hintButton()).toBeNull()
  })

  it('test_fr_s2_chosen_category_not_overridden', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Achievement'))

    await tapSuggest()

    expect(selected()).toEqual(['Achievement'])
    const hint = hintButton() as HTMLButtonElement
    expect(hint.textContent).toBe('Suggested: Learning')
    expect(hint.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    // Next to the chips: after them, before the date.
    expect(categoryGroup().compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(hint.compareDocumentPosition(dateInput()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    // One tap applies it, as the user's own choice; focus moves to that chip.
    await click(hint)
    expect(selected()).toEqual(['Learning'])
    expect(hintButton()).toBeNull()
    expect(document.activeElement).toBe(categoryChip('Learning'))
    expect(discardButton()).not.toBeNull()

    // "Discard suggestions" keeps it.
    await click(discardButton() as HTMLButtonElement)
    expect(selected()).toEqual(['Learning'])
  })

  it('test_fr_s2_the_same_category_changes_nothing', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))

    await tapSuggest()

    expect(selected()).toEqual(['Learning'])
    expect(hintButton()).toBeNull()
    expect(discardButton()).toBeNull()
  })

  it('test_fr_s2_on_the_edit_page_the_category_shows_as_the_hint', async () => {
    await renderAt(EDIT_PATH)

    await tapSuggest()

    expect(selected()).toEqual(['Feedback'])
    expect(hintButton()?.textContent).toBe('Suggested: Learning')
  })

  it('test_fr_s2_tapping_a_chip_removes_the_mark', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    expect(selected()).toEqual(['Learning, suggested'])

    // The suggested chip itself.
    fireEvent.click(categoryChip('Learning'))
    expect(selected()).toEqual(['Learning'])
    expect(categoryChip('Learning').className).not.toContain('chip--suggested')
    // The suggested tags are still there, so "Discard suggestions" stays; it keeps the category.
    await click(discardButton() as HTMLButtonElement)
    expect(selected()).toEqual(['Learning'])
    expect(addedTags()).toEqual([])
  })

  it('test_fr_s2_tapping_another_chip_takes_the_suggested_category_over', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    fireEvent.click(categoryChip('Feedback'))

    expect(selected()).toEqual(['Feedback'])
    expect(discardButton()).toBeNull()
  })

  it('test_fr_s2_the_hint_stays_while_the_chosen_category_differs_and_goes_once_it_is_the_same', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Achievement'))
    await tapSuggest()

    fireEvent.click(categoryChip('Feedback'))
    expect(hintButton()?.textContent).toBe('Suggested: Learning')

    fireEvent.click(categoryChip('Learning'))
    expect(hintButton()).toBeNull()
    expect(selected()).toEqual(['Learning'])
    expect(discardButton()).toBeNull()
  })
})

describe('tags (FR-S2, §7.3)', () => {
  it('test_fr_s2_suggested_tags_are_merged_without_duplicates_and_marked', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['Python', 'Mock tag', 'Testing'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    openFold()
    type(tagInput(), 'python,ci,')

    await tapSuggest()

    // "python" is already there (ignoring case): it keeps its spelling and stays unmarked.
    // The new ones come at the end, in the API's spelling, marked.
    expect(addedTags()).toEqual(['python', 'ci', 'Mock tag', 'Testing'])
    expect(spokenTags()).toEqual(['python', 'ci', 'Mock tag, suggested', 'Testing, suggested'])
    const marked = document.querySelectorAll('.tag-chip--suggested')
    expect(marked).toHaveLength(2)
    const mark = marked[0]?.querySelector('.tag-chip__mark') as HTMLElement
    expect(mark.textContent).toBe('Suggested')
    expect(mark.getAttribute('aria-hidden')).toBe('true')
    expect(mark.querySelector('svg')).not.toBeNull()
  })

  it('test_fr_s2_suggested_tags_open_the_fold_without_moving_the_cursor', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    textArea().focus()
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')

    await act(async () => {
      fireEvent.click(suggestButton())
    })

    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(addedTags()).toEqual(['Python', 'Mock tag'])
    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_s2_the_fold_stays_as_it_is_when_no_tag_is_added', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['PYTHON'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    openFold()
    type(tagInput(), 'python,')
    fireEvent.click(foldButton())
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')

    await tapSuggest()

    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    openFold()
    expect(spokenTags()).toEqual(['python'])
  })

  it('test_fr_s2_one_suggested_tag_can_be_removed', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    fireEvent.click(screen.getByRole('button', { name: 'Remove Mock tag' }))

    expect(spokenTags()).toEqual(['Python, suggested'])
    expect(document.activeElement).toBe(tagInput())
  })

  it('test_fr_s2_typing_a_suggested_tag_name_makes_it_the_users_own', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['Python', 'Mock tag'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    type(tagInput(), 'mock TAG')
    key(tagInput(), 'Enter')
    type(tagInput(), 'python,')

    expect(addedTags()).toEqual(['Python', 'Mock tag'])
    expect(spokenTags()).toEqual(['Python', 'Mock tag'])
    expect(discardButton()).not.toBeNull()

    // "Discard suggestions" keeps them: only the category was still suggested.
    await click(discardButton() as HTMLButtonElement)
    expect(addedTags()).toEqual(['Python', 'Mock tag'])
    expect(selected()).toEqual([])
  })

  it('test_fr_s2_closing_the_fold_keeps_suggested_tags_and_they_are_saved', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    fireEvent.click(foldButton())
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ tags: ['Python', 'Mock tag'] }))
  })
})

describe('discarding and asking again (FR-S2, FR-S3)', () => {
  it('test_fr_s3_discard_suggestions', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['Python', 'Mock tag'] })
    await renderAt('/entries/new')
    expect(discardButton()).toBeNull()
    type(textArea(), 'Learned about pytest')
    openFold()
    type(tagInput(), 'mine,')

    await tapSuggest()
    const discard = discardButton() as HTMLButtonElement
    expect(discard).not.toBeNull()
    expect(discard.className).toContain('quiet-action')
    // Next to the suggest button.
    expect(discard.parentElement?.contains(suggestButton())).toBe(true)

    await click(discard)

    expect(addedTags()).toEqual(['mine'])
    expect(selected()).toEqual([])
    expect(hintButton()).toBeNull()
    expect(discardButton()).toBeNull()
    // The fold stays open; focus moves to the suggest button.
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(document.activeElement).toBe(suggestButton())
  })

  it('test_fr_s3_discard_removes_the_hint_and_keeps_the_users_category', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()
    expect(hintButton()).not.toBeNull()

    await click(discardButton() as HTMLButtonElement)

    expect(hintButton()).toBeNull()
    expect(selected()).toEqual(['Feedback'])
    expect(discardButton()).toBeNull()
  })

  it('test_fr_s2_editing_the_text_keeps_the_suggestions', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    type(textArea(), 'Learned about pytest fixtures and marks')
    await act(async () => {})

    expect(suggest).toHaveBeenCalledTimes(1)
    expect(selected()).toEqual(['Learning, suggested'])
    expect(spokenTags()).toEqual(['Python, suggested', 'Mock tag, suggested'])
  })

  it('test_fr_s2_asking_again_replaces_the_earlier_suggestions', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    openFold()
    type(tagInput(), 'mine,')
    await tapSuggest()
    expect(spokenTags()).toEqual(['mine', 'Python, suggested', 'Mock tag, suggested'])

    suggest.mockResolvedValue({ category: 'Side project', tags: ['Mock tag', 'Rust'] })
    await tapSuggest()

    expect(selected()).toEqual(['Side project, suggested'])
    expect(spokenTags()).toEqual(['mine', 'Mock tag, suggested', 'Rust, suggested'])
    expect(hintButton()).toBeNull()
  })

  it('test_fr_s2_asking_again_drops_an_earlier_hint', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()

    suggest.mockResolvedValue({ category: 'Feedback', tags: [] })
    await tapSuggest()

    expect(hintButton()).toBeNull()
    expect(selected()).toEqual(['Feedback'])
    expect(discardButton()).toBeNull()
  })

  it('test_fr_s2_a_failed_second_request_keeps_the_earlier_suggestions', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    suggest.mockRejectedValue(new api.AiUnavailableError('The AI provider failed.', 503))
    await tapSuggest()

    expect(selected()).toEqual(['Learning, suggested'])
    expect(spokenTags()).toEqual(['Python, suggested', 'Mock tag, suggested'])
    expect(notice()).toBe(UNAVAILABLE)
    expect(discardButton()).not.toBeNull()
  })

  it('test_fr_s2_rules_apply_to_the_form_as_it_is_when_the_answer_arrives', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()
    // While the request runs, the user picks a category and adds a tag.
    fireEvent.click(categoryChip('Achievement'))
    openFold()
    type(tagInput(), 'PYTHON,')
    await answer.resolve({ category: 'Learning', tags: ['Python', 'Mock tag'] })

    expect(selected()).toEqual(['Achievement'])
    expect(hintButton()?.textContent).toBe('Suggested: Learning')
    expect(spokenTags()).toEqual(['PYTHON', 'Mock tag, suggested'])
  })

  it('test_fr_s2_asking_again_while_the_user_changed_things_keeps_their_choices', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    // The user takes the category over, then asks again.
    fireEvent.click(categoryChip('Learning'))

    suggest.mockResolvedValue({ category: 'Feedback', tags: [] })
    await tapSuggest()

    expect(selected()).toEqual(['Learning'])
    expect(hintButton()?.textContent).toBe('Suggested: Feedback')
    expect(addedTags()).toEqual([])
  })
})

describe('saving (FR-S2, §7.3)', () => {
  it('test_fr_s2_suggestions_not_saved_until_confirmed', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['Python', 'Mock tag'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()
    expect(createEntry).not.toHaveBeenCalled()
    expect(updateEntry).not.toHaveBeenCalled()

    // The user changes things, then saves: exactly the form, nothing about suggestions.
    fireEvent.click(screen.getByRole('button', { name: 'Remove Python' }))
    type(tagInput(), 'mine,')
    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0]?.[0]).toEqual({
      text: 'Learned about pytest',
      date: dateInput().value,
      category: 'Learning',
      tags: ['Mock tag', 'mine'],
      result_impact: '',
    })
  })

  it('test_fr_s2_suggestions_on_the_edit_page_are_saved_only_with_save_entry', async () => {
    const { router } = await renderAt(EDIT_PATH)

    await tapSuggest()
    expect(updateEntry).not.toHaveBeenCalled()
    await click(hintButton() as HTMLButtonElement)
    await save()

    expect(updateEntry).toHaveBeenCalledWith(ENTRY_ID, {
      text: 'Led the incident review',
      date: '2026-10-05',
      category: 'Learning',
      tags: ['Leadership', 'incident', 'Python', 'Mock tag'],
      result_impact: 'Fewer pages at night',
    })
    expect(router.state.location.pathname).toBe('/')
  })

  it('test_fr_s2_save_works_while_asking_and_a_late_answer_changes_nothing', async () => {
    const answer = pendingSuggestion()
    const saving = deferred<api.Entry>()
    createEntry.mockImplementation(() => saving.promise)
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    fireEvent.click(categoryChip('Feedback'))

    await save()
    expect(createEntry).toHaveBeenCalledTimes(1)

    // Not the form being saved.
    await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })
    expect(selected()).toEqual(['Feedback'])
    expect(hintButton()).toBeNull()
    expect(addedTags()).toEqual([])
    expect(notice()).toBe('')
    expect(createEntry.mock.calls[0]?.[0]).toEqual(expect.objectContaining({ category: 'Feedback', tags: [] }))
    await act(async () => {
      saving.resolve(entryFrom({ text: 'Learned about pytest', date: '2026-11-12', category: 'Feedback' }))
    })
    expect(savedBand()).toBe('Entry saved.')
  })

  it.each([
    ['an answer', (answer: ReturnType<typeof pendingSuggestion>) => answer.resolve({ category: 'Learning', tags: ['Mock tag'] })],
    ['a failure', (answer: ReturnType<typeof pendingSuggestion>) => answer.reject(new api.AiUnavailableError('x', 503))],
  ])('test_fr_s2_%s_after_saving_does_not_reach_the_new_empty_form', async (_case, finish) => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    fireEvent.click(categoryChip('Feedback'))
    await save()
    expect(savedBand()).toBe('Entry saved.')

    await finish(answer)

    expect(textArea().value).toBe('')
    expect(selected()).toEqual([])
    expect(addedTags()).toEqual([])
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    expect(notice()).toBe('')
    expect(discardButton()).toBeNull()
  })

  it('test_fr_s2_a_late_answer_does_not_reach_the_page_the_user_went_to', async () => {
    const answer = pendingSuggestion()
    const { router } = await renderAt(EDIT_PATH)
    await tapSuggest()
    await save()
    expect(router.state.location.pathname).toBe('/')

    await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })

    expect(router.state.location.pathname).toBe('/')
    expect(document.querySelector('.entry-form')).toBeNull()
    expect(document.body.textContent).not.toContain('Suggested')
  })

  it('test_fr_s2_after_saving_the_reset_form_has_no_suggestions', async () => {
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['Mock tag'] })
    suggest.mockRejectedValueOnce(new api.AiUnavailableError('x', 503))
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()
    // A failed second try leaves the notice and the earlier suggestions.
    await tapSuggest()
    expect(notice()).toBe(UNAVAILABLE)
    expect(hintButton()).not.toBeNull()

    await save()

    expect(savedBand()).toBe('Entry saved.')
    expect(selected()).toEqual([])
    expect(hintButton()).toBeNull()
    expect(discardButton()).toBeNull()
    expect(notice()).toBe('')
    expect(document.querySelectorAll('.chip--suggested, .tag-chip--suggested')).toHaveLength(0)
    expect(suggestButton().disabled).toBe(true)
  })

  it('test_fr_s2_while_saving_discard_and_the_hint_do_nothing', async () => {
    const saving = deferred<api.Entry>()
    createEntry.mockImplementation(() => saving.promise)
    suggest.mockResolvedValue({ category: 'Learning', tags: ['Mock tag'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()

    await save()
    await click(hintButton() as HTMLButtonElement)
    await click(discardButton() as HTMLButtonElement)

    expect(selected()).toEqual(['Feedback'])
    expect(hintButton()).not.toBeNull()
    expect(spokenTags()).toEqual(['Mock tag, suggested'])
    await act(async () => {
      saving.resolve(entryFrom({ text: 'Learned about pytest', date: '2026-11-12', category: 'Feedback' }))
    })
  })
})

describe('the leave prompt (#27)', () => {
  it('test_fr_s2_suggested_values_count_as_unsaved_changes', async () => {
    const { router } = await renderAt(EDIT_PATH)
    await tapSuggest()

    await click(navLink('Review'))

    expect(dialogOpen()).toBe(true)
    expect(router.state.location.pathname).toBe(EDIT_PATH)
  })

  it('test_fr_s3_after_discarding_back_to_the_start_leaving_does_not_ask', async () => {
    const { router } = await renderAt(EDIT_PATH)
    await tapSuggest()
    await click(discardButton() as HTMLButtonElement)

    await click(navLink('Review'))

    expect(dialogOpen()).toBe(false)
    expect(router.state.location.pathname).toBe('/review')
  })

  it('test_fr_s3_after_discarding_on_the_capture_screen_only_the_text_is_unsaved', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    await click(discardButton() as HTMLButtonElement)
    type(textArea(), '')

    await click(navLink('Review'))

    expect(dialogOpen()).toBe(false)
    expect(router.state.location.pathname).toBe('/review')
  })
})

describe('when suggestions fail (§7.3, §8)', () => {
  it.each([
    ['ai_unavailable', new api.AiUnavailableError('The AI provider timed out.', 503), UNAVAILABLE],
    ['the user limit', new api.LimitReachedError('Limit reached.', 429, 'user_suggestions'), USER_LIMIT],
    ['the global limit', new api.LimitReachedError('Limit reached.', 429, 'global'), GLOBAL_LIMIT],
    ['a limit naming no limit', new api.LimitReachedError('Limit reached.', 429, null), UNAVAILABLE],
    ['a limit naming another limit', new api.LimitReachedError('Limit reached.', 429, 'user_summaries'), UNAVAILABLE],
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a validation error', new api.ValidationError('Bad text.', 422, [{ field: 'text', reason: 'x' }]), GENERIC_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_s1_%s_shows_its_notice_and_the_form_stays_usable', async (_case, error, message) => {
    suggest.mockRejectedValueOnce(error)
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()

    const region = document.querySelector('.entry-form__notice') as HTMLElement
    expect(region.textContent).toBe(message)
    expect(region.getAttribute('role')).toBe('status')
    expect(region.className).toContain('message--info')
    expect(region.textContent).not.toContain(error.message)
    // Under the suggest button, before the category.
    expect(suggestButton().compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(region.compareDocumentPosition(categoryGroup()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(selected()).toEqual([])
    expect(discardButton()).toBeNull()

    // The button stays usable and the form still saves.
    expect(suggestButton().disabled).toBe(false)
    fireEvent.click(categoryChip('Learning'))
    await save()
    expect(createEntry).toHaveBeenCalledTimes(1)
  })

  it('test_fr_s1_the_notice_region_stays_in_the_page_while_empty', async () => {
    await renderAt('/entries/new')

    const region = document.querySelector('.entry-form__notice') as HTMLElement
    expect(region.getAttribute('role')).toBe('status')
    expect(region.textContent).toBe('')
  })

  it('test_fr_s1_the_notice_goes_when_asking_again', async () => {
    suggest.mockRejectedValueOnce(new api.NetworkError())
    const answer = deferred<Suggestion>()
    suggest.mockImplementationOnce(() => answer.promise)
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    expect(notice()).toBe(NETWORK_MESSAGE)

    await tapSuggest()
    expect(notice()).toBe('')

    await act(async () => {
      answer.resolve({ category: 'Learning', tags: [] })
    })
    expect(notice()).toBe('')
    expect(selected()).toEqual(['Learning, suggested'])
  })

  it('test_fr_s1_the_notice_is_replaced_by_the_new_outcome', async () => {
    suggest.mockRejectedValueOnce(new api.NetworkError())
    suggest.mockRejectedValueOnce(new api.LimitReachedError('Limit reached.', 429, 'global'))
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')

    await tapSuggest()
    expect(notice()).toBe(NETWORK_MESSAGE)
    await tapSuggest()
    expect(notice()).toBe(GLOBAL_LIMIT)
    expect(document.querySelectorAll('.entry-form__notice')).toHaveLength(1)
  })

  it('test_fr_s1_the_notice_goes_when_save_entry_is_tapped', async () => {
    suggest.mockRejectedValueOnce(new api.AiUnavailableError('x', 503))
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    expect(notice()).toBe(UNAVAILABLE)

    // Even when saving stops at a missing category.
    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(notice()).toBe('')
  })

  it('test_fr_s1_an_expired_login_goes_to_the_login_page_without_asking', async () => {
    const { router } = await renderAt(EDIT_PATH)
    type(textArea(), 'Unsaved change')
    const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
    expect(redirect).toBeDefined()
    suggest.mockImplementationOnce(async () => {
      // As the client does on a 401: remove the session, call the redirect, then throw.
      removeTestSession()
      redirect?.()
      throw new api.NotAuthenticatedError('Not authenticated.', 401)
    })

    await tapSuggest()

    expect(router.state.location.pathname).toBe('/login')
    expect(dialogOpen()).toBe(false)
  })
})

// --- #86: feedback when a suggestion adds nothing or is dropped ---

const NOTHING_NEW = 'No new suggestions for this text.'
const TAGS_LEFT_OUT = 'Up to 10 tags per entry, so not every suggested tag was added.'
const TOO_MANY_TAGS = 'Up to 10 tags per entry.'
const CATEGORY_MESSAGE = 'Choose a category, then save.'
const ENTRY_GONE = "This entry no longer exists, so it can't be saved."
const TEN_TAGS = Array.from({ length: 10 }, (_, index) => `Tag ${index}`)
const EIGHT_TAGS = TEN_TAGS.slice(0, 8)

function noticeRegion(): HTMLElement {
  return document.querySelector('.entry-form__notice') as HTMLElement
}

/** Adds tags through the tag input, each ended by a comma, so none comes from the list. */
function addTags(names: readonly string[]): void {
  openFold()
  type(tagInput(), `${names.join(',')},`)
}

/** The notice shows `text` in the existing polite live region, with the info look (#28). */
function expectInfoNotice(text: string): void {
  const region = noticeRegion()
  expect(region.textContent).toBe(text)
  expect(region.getAttribute('role')).toBe('status')
  expect(region.className).toContain('message--info')
  expect(region.className).not.toContain('message--error')
  expect(document.querySelectorAll('.entry-form__notice')).toHaveLength(1)
  // Never in an alert.
  for (const alert of document.querySelectorAll('[role="alert"]')) {
    expect(alert.textContent).not.toContain(text)
  }
}

/** A suggestion never gives the tag field a message or the error state (#43). */
function expectNoTagMessage(): void {
  expect(messagesOf('entry-tags')).toEqual([])
  expect(tagInput().getAttribute('aria-invalid')).toBe('false')
}

function expectSuggestReady(): void {
  expect(suggestButton().textContent).toBe('Suggest category and tags')
  expect(suggestButton().disabled).toBe(false)
  expect(suggestButton().getAttribute('aria-busy')).toBe('false')
}

function expectSuggestBusy(): void {
  expect(suggestButton().textContent).toBe('Suggesting…')
  expect(suggestButton().getAttribute('aria-busy')).toBe('true')
  expect(suggestButton().getAttribute('aria-disabled')).toBe('true')
}

function firstChip(): HTMLButtonElement {
  return categoryGroup().querySelector('button') as HTMLButtonElement
}

describe('an answer that brings nothing new (#86 A, FR-S2)', () => {
  it('test_fr_s2_an_answer_with_nothing_new_shows_a_notice', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['PYTHON', 'ci'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(['python', 'ci'])
    const region = noticeRegion()
    suggestButton().focus()

    await tapSuggest()

    expectInfoNotice(NOTHING_NEW)
    // The same element as before: it was already in the page, so it is announced.
    expect(noticeRegion()).toBe(region)
    // The answer is applied by #28's rules: here it changes nothing.
    expect(selected()).toEqual(['Learning'])
    expect(hintButton()).toBeNull()
    expect(spokenTags()).toEqual(['python', 'ci'])
    expect(discardButton()).toBeNull()
    expectNoTagMessage()
    // Focus is back on the button (#84).
    expect(document.activeElement).toBe(suggestButton())
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_s2_the_chosen_category_with_no_tags_shows_the_nothing_new_notice', async () => {
    // The contract allows an answer with 0 tags.
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))

    await tapSuggest()

    expectInfoNotice(NOTHING_NEW)
    expect(selected()).toEqual(['Learning'])
    expect(addedTags()).toEqual([])
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
  })

  it('test_fr_s2_the_entrys_own_category_and_tags_on_the_edit_page_show_the_nothing_new_notice', async () => {
    suggest.mockResolvedValue({ category: 'Feedback', tags: ['leadership', 'INCIDENT'] })
    await renderAt(EDIT_PATH)

    await tapSuggest()

    expectInfoNotice(NOTHING_NEW)
    expect(selected()).toEqual(['Feedback'])
    expect(hintButton()).toBeNull()
    expect(spokenTags()).toEqual(['Leadership', 'incident'])
    expect(discardButton()).toBeNull()
    expect(updateEntry).not.toHaveBeenCalled()
  })

  it('test_fr_s2_asking_again_with_the_same_answer_shows_the_notice_again', async () => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    expect(notice()).toBe('')
    expect(selected()).toEqual(['Learning, suggested'])

    for (let round = 0; round < 2; round += 1) {
      const answer = pendingSuggestion()
      await tapSuggest()
      // The notice empties on the tap, so the same text is announced again.
      expect(notice()).toBe('')
      expectSuggestBusy()

      await answer.resolve({ category: 'Learning', tags: ['Python', 'Mock tag'] })

      // The same marks and "Discard suggestions" come back, then the notice shows.
      expect(selected()).toEqual(['Learning, suggested'])
      expect(spokenTags()).toEqual(['Python, suggested', 'Mock tag, suggested'])
      expect(discardButton()).not.toBeNull()
      expectInfoNotice(NOTHING_NEW)
    }
  })

  it('test_fr_s2_asking_again_when_the_new_answer_adds_nothing_shows_the_notice', async () => {
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['Python'] })
    suggest.mockResolvedValueOnce({ category: 'Feedback', tags: ['MINE'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    addTags(['mine'])
    await tapSuggest()
    expect(hintButton()?.textContent).toBe('Suggested: Learning')
    expect(spokenTags()).toEqual(['mine', 'Python, suggested'])
    expect(notice()).toBe('')

    await tapSuggest()

    // The earlier suggestions are removed first (#28), then the notice shows.
    expect(hintButton()).toBeNull()
    expect(spokenTags()).toEqual(['mine'])
    expect(discardButton()).toBeNull()
    expect(selected()).toEqual(['Feedback'])
    expectInfoNotice(NOTHING_NEW)
  })

  it.each([
    ['an empty category filled', null, { category: 'Learning' as const, tags: [] }],
    ['a new hint', 'Feedback', { category: 'Learning' as const, tags: [] }],
    ['a new tag', 'Learning', { category: 'Learning' as const, tags: ['python', 'Rust'] }],
  ])('test_fr_s2_an_answer_with_%s_shows_no_notice', async (_case, chosen, suggestion) => {
    suggest.mockResolvedValue(suggestion)
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    if (chosen !== null) {
      fireEvent.click(categoryChip(chosen))
    }
    addTags(['python'])

    await tapSuggest()

    expect(discardButton()).not.toBeNull()
    expect(notice()).toBe('')
  })
})

describe('suggested tags left out at 10 (#86 B, FR-S2)', () => {
  it('test_fr_s2_tags_left_out_at_10_show_a_notice', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['One', 'Two', 'Three'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(EIGHT_TAGS)
    fireEvent.click(foldButton())
    suggestButton().focus()

    await tapSuggest()

    // The first 2 are added and marked, as #43 says, and the fold opens for them.
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(spokenTags()).toEqual([...EIGHT_TAGS, 'One, suggested', 'Two, suggested'])
    expect(discardButton()).not.toBeNull()
    expectInfoNotice(TAGS_LEFT_OUT)
    expectNoTagMessage()
    expect(document.activeElement).toBe(suggestButton())
  })

  it.each([
    ['an empty category, which is filled and marked', null, ['Learning, suggested'], null],
    ['another chosen category, which gets the hint', 'Feedback', ['Feedback'], 'Suggested: Learning'],
    ['the same chosen category, so nothing else is new', 'Learning', ['Learning'], null],
  ])('test_fr_s2_at_10_tags_no_tag_is_added_and_the_notice_shows_with_%s', async (_case, chosen, chips, hint) => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['tag 0', 'One'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    if (chosen !== null) {
      fireEvent.click(categoryChip(chosen))
    }
    addTags(TEN_TAGS)

    await tapSuggest()

    expect(spokenTags()).toEqual(TEN_TAGS)
    expect(selected()).toEqual(chips)
    expect(hintButton()?.textContent ?? null).toBe(hint)
    expect(discardButton() !== null).toBe(chosen !== 'Learning')
    // The tag-limit text wins over "No new suggestions for this text.".
    expectInfoNotice(TAGS_LEFT_OUT)
    expectNoTagMessage()
  })

  it('test_fr_s2_at_10_tags_suggested_tags_already_on_the_entry_show_the_nothing_new_notice', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['TAG 0', 'tag 9'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(TEN_TAGS)

    await tapSuggest()

    expect(spokenTags()).toEqual(TEN_TAGS)
    expectInfoNotice(NOTHING_NEW)
    expectNoTagMessage()
  })

  it('test_fr_s2_asking_again_with_8_own_tags_and_2_earlier_suggested_tags', async () => {
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['One', 'Two'] })
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['Three', 'Four'] })
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['Five', 'Six', 'Seven'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(EIGHT_TAGS)
    await tapSuggest()
    expect(addedTags()).toEqual([...EIGHT_TAGS, 'One', 'Two'])
    expect(notice()).toBe('')

    // The 2 earlier ones are removed first, so 2 new tags fit: no notice.
    await tapSuggest()
    expect(spokenTags()).toEqual([...EIGHT_TAGS, 'Three, suggested', 'Four, suggested'])
    expect(notice()).toBe('')

    // A third new tag is left out.
    await tapSuggest()
    expect(spokenTags()).toEqual([...EIGHT_TAGS, 'Five, suggested', 'Six, suggested'])
    expectInfoNotice(TAGS_LEFT_OUT)
    expectNoTagMessage()
  })
})

describe('the answer notices (#86 C)', () => {
  it('test_fr_s2_one_notice_element_for_every_outcome_one_text_at_a_time', async () => {
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: [] })
    suggest.mockRejectedValueOnce(new api.AiUnavailableError('x', 503))
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['One'] })
    suggest.mockResolvedValueOnce({ category: 'Feedback', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(TEN_TAGS)
    const region = noticeRegion()
    expect(region.textContent).toBe('')

    await tapSuggest()
    expectInfoNotice(NOTHING_NEW)
    // The next outcome replaces it: a failure shows only its own text.
    await tapSuggest()
    expectInfoNotice(UNAVAILABLE)
    await tapSuggest()
    expectInfoNotice(TAGS_LEFT_OUT)
    // Something new: no notice.
    await tapSuggest()
    expect(hintButton()?.textContent).toBe('Suggested: Feedback')
    expect(notice()).toBe('')
    expect(noticeRegion()).toBe(region)
  })

  it.each([
    ['nothing new', { category: 'Learning' as const, tags: [] }, NOTHING_NEW],
    ['a tag left out', { category: 'Learning' as const, tags: ['One'] }, TAGS_LEFT_OUT],
  ])('test_fr_s2_the_notice_for_%s_never_moves_focus', async (_case, suggestion, text) => {
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    addTags(TEN_TAGS)

    // On the button: back on it after the answer.
    suggestButton().focus()
    let answer = pendingSuggestion()
    await tapSuggest()
    expect(document.activeElement).toBe(suggestButton())
    await answer.resolve(suggestion)
    expect(notice()).toBe(text)
    expect(document.activeElement).toBe(suggestButton())

    // Moved elsewhere while waiting: it stays there.
    answer = pendingSuggestion()
    await tapSuggest()
    dateInput().focus()
    await answer.resolve(suggestion)
    expect(notice()).toBe(text)
    expect(document.activeElement).toBe(dateInput())
  })

  it('test_fr_s2_the_answer_notice_goes_on_the_next_tap_and_on_save_entry', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: [] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    await tapSuggest()
    expect(notice()).toBe(NOTHING_NEW)

    const answer = pendingSuggestion()
    await tapSuggest()
    expect(notice()).toBe('')
    await answer.resolve({ category: 'Learning', tags: [] })
    expect(notice()).toBe(NOTHING_NEW)

    // Save entry: the notice goes, even when the check stops the save.
    type(dateInput(), '')
    await save()
    expect(createEntry).not.toHaveBeenCalled()
    expect(notice()).toBe('')
  })

  it('test_fr_s2_discard_editing_and_changing_tags_or_category_leave_the_notice', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['One', 'Two', 'Three'] })
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    addTags(EIGHT_TAGS)
    await tapSuggest()
    expect(selected()).toEqual(['Learning, suggested'])
    expect(notice()).toBe(TAGS_LEFT_OUT)

    await click(discardButton() as HTMLButtonElement)
    expect(addedTags()).toEqual(EIGHT_TAGS)
    expect(notice()).toBe(TAGS_LEFT_OUT)

    type(textArea(), 'Learned about pytest fixtures')
    expect(notice()).toBe(TAGS_LEFT_OUT)

    fireEvent.click(screen.getByRole('button', { name: 'Remove Tag 0' }))
    type(tagInput(), 'new tag,')
    expect(notice()).toBe(TAGS_LEFT_OUT)

    fireEvent.click(categoryChip('Feedback'))
    expect(notice()).toBe(TAGS_LEFT_OUT)
    expect(suggest).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['nothing new', 'Learning'],
    ['a tag left out', null],
  ])('test_fr_s1_a_failed_request_shows_only_its_failure_notice_where_%s_would_apply', async (_case, chosen) => {
    suggest.mockResolvedValueOnce({ category: 'Learning', tags: ['One'] })
    suggest.mockRejectedValueOnce(new api.LimitReachedError('Limit reached.', 429, 'user_suggestions'))
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    if (chosen !== null) {
      fireEvent.click(categoryChip(chosen))
    }
    addTags(chosen === null ? TEN_TAGS : [])
    await tapSuggest()

    await tapSuggest()

    expectInfoNotice(USER_LIMIT)
  })
})

describe('Save entry while a suggestion is on its way (#86 D, FR-S1)', () => {
  it('test_fr_s1_a_save_stopped_by_the_check_keeps_the_suggestion_coming', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()

    // No category chosen: the check stops the save.
    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-category')).toEqual([CATEGORY_MESSAGE])
    expect(document.activeElement).toBe(firstChip())
    expect(notice()).toBe('')
    // The request keeps running: the button stays busy, and Save entry is ready.
    expectSuggestBusy()
    expect(saveButton().textContent).toBe('Save entry')
    expect(saveButton().getAttribute('aria-busy')).toBe('false')

    await answer.resolve({ category: 'Learning', tags: ['Python', 'Mock tag'] })

    // Applied by #28's rules to the form as it is now.
    expect(selected()).toEqual(['Learning, suggested'])
    expect(spokenTags()).toEqual(['Python, suggested', 'Mock tag, suggested'])
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(discardButton()).not.toBeNull()
    // A category is chosen now, so its message goes; the category is new, so no notice.
    expect(messagesOf('entry-category')).toEqual([])
    expect(notice()).toBe('')
    expectSuggestReady()
    // Focus stays on the chip the check focused.
    expect(document.activeElement).toBe(firstChip())
    // Nothing is saved until Save entry is tapped again.
    expect(createEntry).not.toHaveBeenCalled()

    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0]?.[0]).toEqual({
      text: 'Learned about pytest',
      date: expect.any(String),
      category: 'Learning',
      tags: ['Python', 'Mock tag'],
      result_impact: '',
    })
    expect(savedBand()).toBe('Entry saved.')
  })

  it.each([
    [
      'the text is over 2,000 characters',
      'entry-text',
      'Shorten the text to 2,000 characters, then save.',
      () => type(textArea(), 'a'.repeat(2001)),
      textArea,
    ],
    ['the date is incomplete', 'entry-date', 'Choose a date, then save.', () => type(dateInput(), ''), dateInput],
    [
      'a tag limit is broken',
      'entry-tags',
      TOO_MANY_TAGS,
      () => {
        addTags(TEN_TAGS)
        type(tagInput(), 'Eleventh')
      },
      tagInput,
    ],
    [
      'the result is over 500 characters',
      'entry-result',
      'Shorten the result to 500 characters, then save.',
      () => {
        openFold()
        type(resultInput(), 'r'.repeat(501))
      },
      resultInput,
    ],
  ])('test_fr_s1_a_save_stopped_because_%s_keeps_the_suggestion_coming', async (_case, field, message, breakIt, focused) => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()
    breakIt()

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf(field)).toEqual([message])
    expect(document.activeElement).toBe(focused())
    // Busy wins over disabled, even with the text over 2,000 characters.
    expectSuggestBusy()

    await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })

    expect(selected()).toEqual(['Feedback'])
    expect(hintButton()?.textContent).toBe('Suggested: Learning')
    expect(messagesOf(field)).toEqual([message])
    expect(document.activeElement).toBe(focused())
    if (field === 'entry-tags') {
      // The tag is left out at 10: the notice says the field's rule in the same words.
      expect(addedTags()).toEqual(TEN_TAGS)
      expectInfoNotice(TAGS_LEFT_OUT)
    } else {
      expect(spokenTags()).toEqual(['Mock tag, suggested'])
      expect(notice()).toBe('')
    }
    if (field === 'entry-text') {
      // Ready again, but disabled with its hint over 2,000 characters (#43).
      expect(suggestButton().disabled).toBe(true)
      expect(suggestButton().getAttribute('aria-busy')).toBe('false')
      expect(document.getElementById('entry-suggest-hint')?.textContent).toBe(
        'Suggestions work on up to 2,000 characters.',
      )
    } else {
      expectSuggestReady()
    }
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_s2_an_answer_after_a_stopped_save_shows_the_nothing_new_notice', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Learning'))
    await tapSuggest()
    type(dateInput(), '')
    await save()
    expect(notice()).toBe('')

    await answer.resolve({ category: 'Learning', tags: [] })

    expectInfoNotice(NOTHING_NEW)
    expect(messagesOf('entry-date')).toEqual(['Choose a date, then save.'])
    expect(document.activeElement).toBe(dateInput())
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_s1_a_request_that_fails_after_a_stopped_save_shows_its_failure_notice', async () => {
    const answer = pendingSuggestion()
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    await tapSuggest()
    await save()
    expect(messagesOf('entry-category')).toEqual([CATEGORY_MESSAGE])

    await answer.reject(new api.AiUnavailableError('The AI provider timed out.', 503))

    expectInfoNotice(UNAVAILABLE)
    expect(messagesOf('entry-category')).toEqual([CATEGORY_MESSAGE])
    expect(selected()).toEqual([])
    expect(document.activeElement).toBe(firstChip())
    expectSuggestReady()
    expect(createEntry).not.toHaveBeenCalled()
  })

  const SAVE_ERRORS: [string, string, unknown, () => void][] = [
    [
      'a server validation error',
      '/entries/new',
      new api.ValidationError('Bad text.', 422, [{ field: 'text', reason: 'x' }]),
      () => expect(messagesOf('entry-text')).toEqual(['Write what happened, then save.']),
    ],
    ['a network error', '/entries/new', new api.NetworkError(), () => expect(formError()).toBe(NETWORK_MESSAGE)],
    ['a deleted entry', EDIT_PATH, new api.NotFoundError('Not found.', 404), () => expect(formError()).toBe(ENTRY_GONE)],
    [
      'another error',
      EDIT_PATH,
      new api.UnknownError('Internal error.', 500, 'internal_error'),
      () => expect(formError()).toBe(GENERIC_MESSAGE),
    ],
  ]

  describe.each(['while saving', 'after the failure'])('the dropped answer arrives %s', (when) => {
    it.each(SAVE_ERRORS)(
      'test_fr_s1_a_sent_save_that_fails_drops_the_suggestion_without_a_notice: %s',
      async (_case, path, error, expectSaveError) => {
        const answer = pendingSuggestion()
        const saving = deferred<api.Entry>()
        createEntry.mockImplementation(() => saving.promise)
        updateEntry.mockImplementation(() => saving.promise)
        await renderAt(path)
        if (path === '/entries/new') {
          type(textArea(), 'Learned about pytest')
          fireEvent.click(categoryChip('Feedback'))
        }
        await tapSuggest()

        await save()

        // Sent: the request is dropped at once, and the suggest button has the disabled look.
        expect(createEntry.mock.calls.length + updateEntry.mock.calls.length).toBe(1)
        expect(saveButton().textContent).toBe('Saving…')
        expect(suggestButton().textContent).toBe('Suggest category and tags')
        expect(suggestButton().disabled).toBe(true)
        expect(suggestButton().getAttribute('aria-busy')).toBe('false')

        if (when === 'while saving') {
          await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })
        }
        await act(async () => {
          saving.reject(error)
        })
        if (when === 'after the failure') {
          await answer.resolve({ category: 'Learning', tags: ['Mock tag'] })
        }

        // Only the save error; the dropped answer changes nothing.
        expectSaveError()
        expect(selected()).toEqual(['Feedback'])
        expect(hintButton()).toBeNull()
        expect(document.querySelectorAll('.chip--suggested, .tag-chip--suggested')).toHaveLength(0)
        expect(discardButton()).toBeNull()
        expect(notice()).toBe('')
        // The suggest button is ready again, so the user can ask again.
        expectSuggestReady()
        suggest.mockResolvedValue({ category: 'Learning', tags: [] })
        await tapSuggest()
        expect(hintButton()?.textContent).toBe('Suggested: Learning')
        expect(suggest).toHaveBeenCalledTimes(2)
      },
    )
  })

  it('test_fr_s1_a_dropped_request_that_fails_after_a_failed_save_shows_no_notice', async () => {
    const answer = pendingSuggestion()
    createEntry.mockRejectedValue(new api.NetworkError())
    await renderAt('/entries/new')
    type(textArea(), 'Learned about pytest')
    fireEvent.click(categoryChip('Feedback'))
    await tapSuggest()
    await save()
    expect(formError()).toBe(NETWORK_MESSAGE)

    await answer.reject(new api.AiUnavailableError('x', 503))

    expect(notice()).toBe('')
    expect(formError()).toBe(NETWORK_MESSAGE)
    expectSuggestReady()
  })

  it('test_fr_s1_a_late_failure_does_not_reach_the_page_the_user_went_to', async () => {
    const answer = pendingSuggestion()
    const { router } = await renderAt(EDIT_PATH)
    await tapSuggest()
    await save()
    expect(router.state.location.pathname).toBe('/')

    await answer.reject(new api.AiUnavailableError('x', 503))

    expect(router.state.location.pathname).toBe('/')
    expect(document.body.textContent).not.toContain(UNAVAILABLE)
  })
})
