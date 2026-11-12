import { act, fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { SAVED_MESSAGE_MS } from '../components/useSavedMessage.ts'
import {
  addStylesheet,
  addedTags,
  categoryGroup,
  chip,
  dateInput,
  entryFrom,
  fillRequired,
  foldButton,
  formError,
  justSavedRows,
  key,
  messagesOf,
  openFold,
  options,
  pressedChips,
  resultInput,
  save,
  saveButton,
  savedBand,
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
    createEntry: vi.fn(),
    listEntries: vi.fn(),
    listTags: vi.fn(),
    suggestCategoryAndTags: vi.fn(),
  }
})

const createEntry = vi.mocked(api.createEntry)
const listEntries = vi.mocked(api.listEntries)
const listTags = vi.mocked(api.listTags)
const suggest = vi.mocked(api.suggestCategoryAndTags)

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
// Sorted as GET /tags sorts them: alphabetically, without regard to case.
const KNOWN_TAGS = ['Leadership', 'pytest', 'Python', 'TypeScript']

// 08:00 on 2 November in Sydney (the test time zone), still 1 November in UTC.
const SYDNEY_MORNING = new Date('2026-11-01T21:00:00Z')

let scrollTo: ReturnType<typeof vi.fn>

/** Renders the capture screen and waits for the tag list request. */
async function renderNewEntry() {
  const result = renderRoute('/entries/new')
  await act(async () => {})
  return result
}

beforeEach(() => {
  storeTestSession()
  listTags.mockResolvedValue({ tags: KNOWN_TAGS })
  // For tests that go to `/`, which loads the list (#29).
  listEntries.mockResolvedValue({ entries: [] })
  createEntry.mockImplementation(async (body) => entryFrom(body))
  scrollTo = vi.fn()
  window.scrollTo = scrollTo as unknown as typeof window.scrollTo
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
})

describe('capture screen (FR-E1, DESIGN.md → Layout)', () => {
  it('test_fr_e1_new_entry_page_shows_the_empty_form_in_the_app_shell', async () => {
    await renderNewEntry()

    const main = screen.getByRole('main')
    expect(within(main).getByRole('heading', { level: 1, name: 'New entry' })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy()
    expect(textArea().value).toBe('')
    expect(pressedChips()).toEqual([])
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    expect(savedBand()).toBe('')
    expect(formError()).toBe('')
  })

  it('test_fr_e1_cursor_starts_in_the_text_field', async () => {
    await renderNewEntry()

    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e1_capture_screen_order_and_no_cancel', async () => {
    await renderNewEntry()

    const order = [
      document.querySelector('.saved-region'),
      screen.getByRole('heading', { level: 1, name: 'New entry' }),
      textArea(),
      categoryGroup(),
      dateInput(),
      foldButton(),
      saveButton(),
    ]
    for (let index = 1; index < order.length; index += 1) {
      const before = order[index - 1] as Node
      const after = order[index] as Node
      expect(before.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Just saved' })).toBeNull()
  })

  it.each(['phone', 'laptop'] as const)('test_entries_is_current_on_the_new_entry_page_on_the_%s', async (width) => {
    setViewport(width)
    await renderNewEntry()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Entries' }).getAttribute('aria-current')).toBe('page')
  })

  it('test_fr_e1_save_entry_is_the_large_primary_button_on_the_phone', async () => {
    await renderNewEntry()

    expect(saveButton().className).toContain('button--primary')
    expect(saveButton().className).toContain('button--large')
    // The only primary (filled plum) button on the page.
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
    expect(foldButton().className).toContain('button--secondary')
  })

  it('test_fr_e1_save_entry_is_the_normal_primary_button_on_the_laptop', async () => {
    setViewport('laptop')
    await renderNewEntry()

    expect(saveButton().className).toContain('button--primary')
    expect(saveButton().className).not.toContain('button--large')
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
  })
})

describe('fields (FR-E2)', () => {
  it('test_fr_e2_text_is_a_multi_line_field_with_a_visible_label', async () => {
    await renderNewEntry()

    expect(textArea().tagName).toBe('TEXTAREA')
    expect(textArea().labels?.[0]?.textContent).toBe('What happened?')
    expect(resultInputLabel()).toBe('Result')
  })

  it('test_fr_e2_categories_are_chips_in_order_with_a_group_label', async () => {
    await renderNewEntry()

    const chips = within(categoryGroup()).getAllByRole('button')
    expect(chips.map((button) => button.textContent)).toEqual(['Achievement', 'Learning', 'Feedback', 'Side project'])
    for (const button of chips) {
      expect(button.getAttribute('aria-pressed')).toBe('false')
      // The category chip, not the filter variant (no check icon).
      expect(button.querySelector('.chip__check')).toBeNull()
    }
    expect(screen.getByText('Category').id).toBe(categoryGroup().getAttribute('aria-labelledby'))
  })

  it('test_fr_e2_tapping_a_chip_selects_it_and_unselects_the_other', async () => {
    await renderNewEntry()

    fireEvent.click(chip('Learning'))
    expect(pressedChips()).toEqual(['Learning'])

    fireEvent.click(chip('Side project'))
    expect(pressedChips()).toEqual(['Side project'])

    // Tapping the selected chip keeps it selected.
    fireEvent.click(chip('Side project'))
    expect(pressedChips()).toEqual(['Side project'])
    expect(chip('Side project').getAttribute('aria-pressed')).toBe('true')
  })

  it('test_fr_e2_date_defaults_to_local_today', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: SYDNEY_MORNING })
    // The test process runs in Australia/Sydney (vite.config.ts): UTC+11 in November.
    expect(new Date().getTimezoneOffset()).toBe(-660)
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-11-01')

    await renderNewEntry()

    expect(dateInput().type).toBe('date')
    expect(dateInput().value).toBe('2026-11-02')
  })

  it('test_fr_e2_any_date_can_be_chosen_including_future_dates', async () => {
    await renderNewEntry()
    fillRequired()
    type(dateInput(), '2031-01-15')

    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ date: '2031-01-15' }))
  })

  it('test_fr_e2_date_input_uses_tabular_figures', async () => {
    const remove = await addStylesheet('components/TextField.css')
    try {
      await renderNewEntry()

      expect(getComputedStyle(dateInput()).fontVariantNumeric).toBe('tabular-nums')
    } finally {
      remove()
    }
  })

  it('test_fr_e2_fold_is_closed_on_a_new_entry_and_opens_and_closes', async () => {
    await renderNewEntry()

    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('combobox', { name: 'Tags' })).toBeNull()
    expect(screen.queryByRole('textbox', { name: 'Result' })).toBeNull()

    fireEvent.click(foldButton())
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(tagInput()).toBeTruthy()
    expect(resultInput().tagName).toBe('TEXTAREA')
    expect(foldButton().getAttribute('aria-controls')).toBe(resultInput().closest('[id="entry-more"]')?.id)

    fireEvent.click(foldButton())
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('combobox', { name: 'Tags' })).toBeNull()
  })
})

function resultInputLabel(): string | null {
  openFold()
  return resultInput().labels?.[0]?.textContent ?? null
}

describe('tags (FR-E3)', () => {
  it('test_fr_e3_typing_lists_matching_tags_ignoring_case_and_choosing_adds_the_stored_spelling', async () => {
    await renderNewEntry()
    openFold()

    type(tagInput(), 'PY')
    expect(tagInput().getAttribute('aria-expanded')).toBe('true')
    expect(options()).toEqual(['pytest', 'Python'])

    // Contains, not only starts with.
    type(tagInput(), 'script')
    expect(options()).toEqual(['TypeScript'])

    type(tagInput(), 'py')
    fireEvent.click(screen.getByRole('option', { name: 'Python' }))
    expect(addedTags()).toEqual(['Python'])
    expect(tagInput().value).toBe('')

    // Added tags are left out of the list.
    type(tagInput(), 'py')
    expect(options()).toEqual(['pytest'])
  })

  it('test_fr_e3_arrow_keys_and_enter_choose_a_tag_and_escape_closes_the_list', async () => {
    await renderNewEntry()
    openFold()

    type(tagInput(), 't')
    expect(options()).toEqual(['pytest', 'Python', 'TypeScript'])
    expect(tagInput().getAttribute('aria-activedescendant')).toBeNull()
    key(tagInput(), 'ArrowDown')
    expect(tagInput().getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'pytest' }).id)
    expect(screen.getByRole('option', { name: 'pytest' }).getAttribute('aria-selected')).toBe('true')
    key(tagInput(), 'ArrowDown')
    key(tagInput(), 'ArrowUp')
    key(tagInput(), 'ArrowUp')
    // Up from the first option wraps to the last.
    expect(screen.getByRole('option', { name: 'TypeScript' }).getAttribute('aria-selected')).toBe('true')
    key(tagInput(), 'ArrowDown')
    key(tagInput(), 'ArrowDown')
    key(tagInput(), 'Enter')
    expect(addedTags()).toEqual(['Python'])

    type(tagInput(), 'lead')
    expect(options()).toEqual(['Leadership'])
    key(tagInput(), 'Escape')
    expect(options()).toEqual([])
    expect(tagInput().getAttribute('aria-expanded')).toBe('false')
    expect(tagInput().value).toBe('lead')
  })

  it('test_fr_e3_enter_and_comma_add_the_typed_text_as_a_new_tag', async () => {
    await renderNewEntry()
    openFold()

    type(tagInput(), 'Mentoring')
    key(tagInput(), 'Enter')
    expect(addedTags()).toEqual(['Mentoring'])
    expect(tagInput().value).toBe('')

    type(tagInput(), 'go,')
    expect(addedTags()).toEqual(['Mentoring', 'go'])
    expect(tagInput().value).toBe('')
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e3_enter_in_the_tag_input_never_saves_the_form', async () => {
    const user = userEvent.setup()
    await renderNewEntry()
    fillRequired()
    openFold()

    await user.click(tagInput())
    await user.keyboard('Rust{Enter}')
    await user.keyboard('{Enter}')

    expect(addedTags()).toEqual(['Rust'])
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e3_pasting_a_comma_separated_list_adds_each_tag', async () => {
    const user = userEvent.setup()
    await renderNewEntry()
    openFold()

    await user.click(tagInput())
    await user.paste('a, b')

    expect(addedTags()).toEqual(['a', 'b'])
    expect(tagInput().value).toBe('')
  })

  it('test_fr_e3_tag_names_are_trimmed_empty_names_ignored_and_duplicates_skipped', async () => {
    await renderNewEntry()
    openFold()

    type(tagInput(), '  rust  ')
    key(tagInput(), 'Enter')
    type(tagInput(), '   ')
    key(tagInput(), 'Enter')
    type(tagInput(), ' , ,')
    type(tagInput(), 'RUST')
    key(tagInput(), 'Enter')

    expect(addedTags()).toEqual(['rust'])
  })

  it('test_fr_e3_each_tag_has_a_named_remove_button', async () => {
    await renderNewEntry()
    openFold()
    type(tagInput(), 'python,go,')

    fireEvent.click(screen.getByRole('button', { name: 'Remove python' }))

    expect(addedTags()).toEqual(['go'])
    expect(document.activeElement).toBe(tagInput())
    fillRequired()
    await save()
    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ tags: ['go'] }))
  })

  it('test_fr_e3_new_tag_names_are_sent_with_the_entry', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    type(tagInput(), 'brand-new,')

    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ tags: ['brand-new'] }))
  })

  it('test_fr_e3_text_left_in_the_tag_input_is_added_on_save', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    type(tagInput(), 'python,')
    type(tagInput(), ' pending ')

    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ tags: ['python', 'pending'] }))
  })

  it('test_fr_e3_a_failed_tag_list_shows_nothing_and_tags_can_be_typed', async () => {
    listTags.mockRejectedValue(new api.NetworkError())
    await renderNewEntry()
    openFold()

    type(tagInput(), 'py')
    expect(options()).toEqual([])
    // No error anywhere: every alert region is empty.
    expect(screen.queryAllByRole('alert', { hidden: true }).map((alert) => alert.textContent)).toEqual(
      screen.queryAllByRole('alert', { hidden: true }).map(() => ''),
    )
    key(tagInput(), 'Enter')
    expect(addedTags()).toEqual(['py'])
  })

  it('test_fr_e3_tags_saved_on_the_capture_screen_are_offered_for_the_next_entry', async () => {
    listTags.mockResolvedValue({ tags: [] })
    // The API answers with the stored spelling.
    createEntry.mockImplementation(async (body) => entryFrom({ ...body, tags: ['Brand-New'] }))
    await renderNewEntry()
    fillRequired()
    openFold()
    type(tagInput(), 'brand-new,')

    await save()
    openFold()
    type(tagInput(), 'brand')

    expect(options()).toEqual(['Brand-New'])
    expect(listTags).toHaveBeenCalledTimes(1)
  })
})

describe('saving (FR-E1, §7.2)', () => {
  it('test_fr_e1_missing_fields_block_saving_with_a_message_under_each', async () => {
    await renderNewEntry()
    type(dateInput(), '')

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-text')).toEqual(['Write what happened, then save.'])
    expect(messagesOf('entry-category')).toEqual(['Choose a category, then save.'])
    expect(messagesOf('entry-date')).toEqual(['Choose a date, then save.'])
    expect(textArea().getAttribute('aria-invalid')).toBe('true')
    expect(dateInput().getAttribute('aria-invalid')).toBe('true')
    expect(categoryGroup().getAttribute('aria-describedby')).toBe('entry-category-messages')
    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e1_cursor_moves_to_the_first_field_with_a_problem_and_messages_go_when_fixed', async () => {
    await renderNewEntry()
    type(dateInput(), '')
    await save()

    type(textArea(), 'Wrote the design doc')
    expect(messagesOf('entry-text')).toEqual([])
    await save()
    expect(document.activeElement).toBe(chip('Achievement'))

    fireEvent.click(chip('Learning'))
    expect(messagesOf('entry-category')).toEqual([])
    await save()
    expect(document.activeElement).toBe(dateInput())

    type(dateInput(), '2026-11-02')
    expect(messagesOf('entry-date')).toEqual([])
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e1_whitespace_only_text_counts_as_empty', async () => {
    await renderNewEntry()
    fillRequired('   \n\t ')

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-text')).toEqual(['Write what happened, then save.'])
    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e1_saving_sends_every_field_as_typed', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: SYDNEY_MORNING })
    await renderNewEntry()
    fillRequired('  Fixed the flaky test\nin CI  ', 'Learning')
    openFold()
    type(tagInput(), 'ci,')
    type(resultInput(), 'Builds are green')

    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry).toHaveBeenCalledWith({
      text: '  Fixed the flaky test\nin CI  ',
      date: '2026-11-02',
      category: 'Learning',
      tags: ['ci'],
      result_impact: 'Builds are green',
    })
  })

  it('test_fr_e1_an_empty_result_is_sent_as_empty', async () => {
    await renderNewEntry()
    fillRequired()

    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ tags: [], result_impact: '' }))
  })

  it('test_fr_e1_double_tap_creates_one_entry', async () => {
    let finish: () => void = () => {}
    createEntry.mockImplementation(
      (body) =>
        new Promise((resolve) => {
          finish = () => resolve(entryFrom(body))
        }),
    )
    await renderNewEntry()
    fillRequired()

    await act(async () => {
      fireEvent.click(saveButton())
      fireEvent.click(saveButton())
    })
    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    await act(async () => {
      finish()
    })
    expect(justSavedRows()).toHaveLength(1)
  })

  it('test_fr_e1_while_saving_the_button_shows_progress_and_fields_cannot_change', async () => {
    let finish: () => void = () => {}
    createEntry.mockImplementation(
      (body) =>
        new Promise((resolve) => {
          finish = () => resolve(entryFrom(body))
        }),
    )
    await renderNewEntry()
    fillRequired('Mentored a new hire')
    openFold()

    await save()

    expect(saveButton().textContent).toBe('Saving…')
    expect(saveButton().disabled).toBe(true)
    expect(saveButton().getAttribute('aria-busy')).toBe('true')
    expect(textArea().readOnly).toBe(true)
    expect(dateInput().readOnly).toBe(true)
    expect(tagInput().readOnly).toBe(true)
    expect(resultInput().readOnly).toBe(true)
    type(textArea(), 'Changed')
    fireEvent.click(chip('Feedback'))
    fireEvent.click(foldButton())
    expect(textArea().value).toBe('Mentored a new hire')
    expect(pressedChips()).toEqual(['Achievement'])
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')

    await act(async () => {
      finish()
    })
    expect(saveButton().textContent).toBe('Save entry')
  })

  it('test_fr_e1_server_validation_errors_show_under_the_named_fields', async () => {
    createEntry.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [
        { field: 'text', reason: 'String should match pattern' },
        { field: 'date', reason: 'Input should be a valid date' },
        { field: 'category', reason: "Input should be 'Achievement'" },
        { field: 'tags.0', reason: 'String should have at most 50 characters' },
        { field: 'result_impact', reason: 'String should have at most 2000 characters' },
      ]),
    )
    await renderNewEntry()
    fillRequired()

    await save()

    expect(messagesOf('entry-text')).toEqual(['Write what happened, then save.'])
    expect(messagesOf('entry-date')).toEqual(['Choose a date, then save.'])
    expect(messagesOf('entry-category')).toEqual(['Choose a category, then save.'])
    // The result error opens "Add tags and result".
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(messagesOf('entry-tags')).toEqual(['Check your tags, then save.'])
    expect(messagesOf('entry-result')).toEqual(['Check the result, then save.'])
    expect(document.body.textContent).not.toContain('String should')
    expect(formError()).toBe('')

    // A field's message goes once it is changed.
    type(resultInput(), 'Shorter')
    expect(messagesOf('entry-result')).toEqual([])
    expect(messagesOf('entry-tags')).toEqual(['Check your tags, then save.'])
  })

  it('test_fr_e1_server_error_on_the_result_opens_the_fold', async () => {
    createEntry.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [{ field: 'result_impact', reason: 'Too long' }]),
    )
    await renderNewEntry()
    fillRequired()
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')

    await save()

    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(messagesOf('entry-result')).toEqual(['Check the result, then save.'])
  })

  it.each([
    ['a field not on the form', [{ field: 'body', reason: 'Field required' }]],
    ['no field', []],
  ])('test_fr_e1_a_server_validation_error_naming_%s_shows_the_general_message', async (_case, fields) => {
    createEntry.mockRejectedValue(new api.ValidationError('The request has invalid fields.', 422, fields))
    await renderNewEntry()
    fillRequired()

    await save()

    expect(formError()).toBe(GENERIC_MESSAGE)
  })

  it.each([
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_e1_%s_shows_a_message_next_to_save_and_keeps_the_input', async (_case, error, message) => {
    createEntry.mockRejectedValueOnce(error)
    await renderNewEntry()
    fillRequired('Ran the retro', 'Feedback')
    openFold()
    type(tagInput(), 'team,')
    type(resultInput(), 'Two actions agreed')

    await save()

    const alert = document.querySelector('.entry-form__error') as HTMLElement
    expect(alert.getAttribute('role')).toBe('alert')
    expect(alert.textContent).toBe(message)
    // Next to Save entry: right before it.
    expect(alert.nextElementSibling?.contains(saveButton())).toBe(true)
    expect(textArea().value).toBe('Ran the retro')
    expect(pressedChips()).toEqual(['Feedback'])
    expect(addedTags()).toEqual(['team'])
    expect(resultInput().value).toBe('Two actions agreed')
    expect(saveButton().disabled).toBe(false)

    // Tapping Save entry again tries again.
    await save()
    expect(createEntry).toHaveBeenCalledTimes(2)
    expect(formError()).toBe('')
    expect(savedBand()).toBe('Entry saved.')
  })

  it('test_fr_e1_saving_never_calls_the_ai', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    type(tagInput(), 'a,')

    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(suggest).not.toHaveBeenCalled()
  })
})

describe('after saving a new entry (DESIGN.md → Layout, Saved message)', () => {
  it('test_fr_e1_stays_on_the_capture_screen_with_the_saved_message_and_a_reset_form', async () => {
    const { router } = await renderNewEntry()
    fillRequired('Presented at the guild', 'Side project')
    openFold()
    type(tagInput(), 'talks,')
    type(resultInput(), '40 people came')
    type(tagInput(), 'left')

    await save()

    expect(router.state.location.pathname).toBe('/entries/new')
    expect(savedBand()).toBe('Entry saved.')
    expect(document.querySelector('.saved-region')?.getAttribute('role')).toBe('status')
    expect(scrollTo).toHaveBeenCalledWith({ top: 0 })
    expect(textArea().value).toBe('')
    expect(pressedChips()).toEqual([])
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')
    openFold()
    expect(addedTags()).toEqual([])
    expect(tagInput().value).toBe('')
    expect(resultInput().value).toBe('')
    expect(messagesOf('entry-text')).toEqual([])
  })

  it('test_fr_e1_after_saving_the_cursor_is_in_the_text_field', async () => {
    await renderNewEntry()
    fillRequired()
    saveButton().focus()

    await save()

    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e2_date_resets_to_local_today_after_a_save_past_midnight', async () => {
    // 23:58 on 2 November in Sydney.
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-02T12:58:00Z') })
    await renderNewEntry()
    expect(dateInput().value).toBe('2026-11-02')
    fillRequired()

    // 00:05 on 3 November in Sydney; still 2 November in UTC.
    vi.setSystemTime(new Date('2026-11-02T13:05:00Z'))
    await save()

    expect(createEntry).toHaveBeenCalledWith(expect.objectContaining({ date: '2026-11-02' }))
    expect(dateInput().value).toBe('2026-11-03')
  })

  it('test_fr_e1_just_saved_lists_the_entries_saved_this_visit_newest_first', async () => {
    await renderNewEntry()
    expect(justSavedRows()).toEqual([])

    fillRequired('First win', 'Achievement')
    type(dateInput(), '2026-11-10')
    await save()
    fillRequired('Second thing I learned', 'Learning')
    type(dateInput(), '2026-11-11')
    openFold()
    type(resultInput(), 'Faster reviews')
    await save()

    const heading = screen.getByRole('heading', { level: 2, name: 'Just saved' })
    expect(saveButton().compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const rows = justSavedRows()
    expect(rows).toHaveLength(2)
    expect(rows[0]?.querySelector('time')?.getAttribute('datetime')).toBe('2026-11-11')
    expect(rows[0]?.textContent).toContain('Learning')
    expect(rows[0]?.textContent).toContain('Second thing I learned')
    expect(rows[0]?.textContent).toContain('Result: Faster reviews')
    expect(rows[1]?.textContent).toContain('10 Nov')
    expect(rows[1]?.textContent).toContain('Achievement')
    expect(rows[1]?.textContent).toContain('First win')
    // As #27 built them: no Edit or Delete and no tags (those are the entries page's, #29).
    for (const row of rows) {
      expect(row.querySelector('a, button, .entry-row__tags')).toBeNull()
    }
    // Kept in the page: no list request.
    expect(listEntries).not.toHaveBeenCalled()
  })

  it('test_fr_e1_leaving_the_page_empties_just_saved', async () => {
    const { router } = await renderNewEntry()
    fillRequired()
    await save()
    expect(justSavedRows()).toHaveLength(1)

    await act(async () => {
      await router.navigate('/')
    })
    await act(async () => {
      await router.navigate('/entries/new')
    })

    expect(justSavedRows()).toEqual([])
    expect(screen.queryByRole('heading', { name: 'Just saved' })).toBeNull()
  })

  it('test_fr_e1_saving_again_keeps_one_message_and_restarts_its_time', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    await renderNewEntry()
    fillRequired('One')
    await save()
    await act(async () => {
      vi.advanceTimersByTime(4_000)
    })

    fillRequired('Two')
    await save()
    expect(document.querySelectorAll('.saved-message')).toHaveLength(1)
    await act(async () => {
      vi.advanceTimersByTime(4_000)
    })
    expect(savedBand()).toBe('Entry saved.')

    await act(async () => {
      vi.advanceTimersByTime(SAVED_MESSAGE_MS - 4_000)
    })
    expect(savedBand()).toBe('')
    expect(justSavedRows().map((row) => row.querySelector('.entry-row__text')?.textContent)).toEqual(['Two', 'One'])
  })
})
