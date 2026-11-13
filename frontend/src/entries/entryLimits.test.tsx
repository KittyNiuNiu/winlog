import { act, fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import {
  ENTRY_ID,
  addedTags,
  entryFrom,
  fillRequired,
  foldButton,
  key,
  messagesOf,
  openFold,
  resultInput,
  save,
  storedEntry,
  tagInput,
  textArea,
  type,
} from '../test/entryForm.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'

// The maximum input sizes on the entry form (#43 and its design note): the counters, the
// checks before saving, the disabled suggest button and the tag limits, on the capture
// screen and the edit page. The API client is mocked: no test makes a real AI call.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    createEntry: vi.fn(),
    getEntry: vi.fn(),
    updateEntry: vi.fn(),
    listEntries: vi.fn(),
    listTags: vi.fn(),
    suggestCategoryAndTags: vi.fn(),
  }
})

const createEntry = vi.mocked(api.createEntry)
const getEntry = vi.mocked(api.getEntry)
const updateEntry = vi.mocked(api.updateEntry)
const listEntries = vi.mocked(api.listEntries)
const listTags = vi.mocked(api.listTags)
const suggest = vi.mocked(api.suggestCategoryAndTags)

const TEXT_TOO_LONG = 'Shorten the text to 2,000 characters, then save.'
const RESULT_TOO_LONG = 'Shorten the result to 500 characters, then save.'
const TAG_TOO_LONG = 'Tags can be up to 40 characters.'
const TOO_MANY_TAGS = 'Up to 10 tags per entry.'
const SUGGEST_HINT = 'Suggestions work on up to 2,000 characters.'
const LONG_TAG = 'x'.repeat(41)
const TEN_TAGS = Array.from({ length: 10 }, (_, index) => `Tag ${index}`)

async function renderNewEntry() {
  renderRoute('/entries/new')
  await act(async () => {})
}

async function renderEdit() {
  renderRoute(`/entries/${ENTRY_ID}/edit`)
  await act(async () => {})
}

/** The counter's visible text under a field, or null when there is none. */
function counterOf(id: string): string | null {
  const counter = document.getElementById(`${id}-counter`)
  return counter === null ? null : (counter.querySelector('[aria-hidden="true"]')?.textContent ?? '')
}

function counterIsOver(id: string): boolean {
  return document.getElementById(`${id}-counter`)?.classList.contains('field__counter--over') ?? false
}

function suggestButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Suggest category and tags|Suggesting…)$/ }) as HTMLButtonElement
}

function suggestHint(): HTMLElement | null {
  return document.getElementById('entry-suggest-hint')
}

function addTag(name: string) {
  type(tagInput(), name)
  key(tagInput(), 'Enter')
}

beforeEach(() => {
  storeTestSession()
  listTags.mockResolvedValue({ tags: [] })
  listEntries.mockResolvedValue({ entries: [] })
  createEntry.mockImplementation(async (body) => entryFrom(body))
  updateEntry.mockImplementation(async (id, body) => entryFrom(body, id))
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('counters (FR-E2)', () => {
  it('test_fr_e2_no_counter_below_80_percent', async () => {
    await renderNewEntry()
    openFold()

    type(textArea(), 'a'.repeat(1599))
    type(resultInput(), 'r'.repeat(399))

    expect(counterOf('entry-text')).toBeNull()
    expect(counterOf('entry-result')).toBeNull()
    expect(textArea().getAttribute('aria-describedby')).toBeNull()
  })

  it('test_fr_e2_counters_from_80_percent', async () => {
    await renderNewEntry()
    openFold()

    type(textArea(), 'a'.repeat(1600))
    type(resultInput(), 'r'.repeat(400))

    expect(counterOf('entry-text')).toBe('1,600 / 2,000')
    expect(counterOf('entry-result')).toBe('400 / 500')
    expect(counterIsOver('entry-text')).toBe(false)
    expect(textArea().getAttribute('aria-describedby')).toBe('entry-text-counter')
    expect(textArea().getAttribute('aria-invalid')).toBe('false')
  })

  it('test_fr_e2_emoji_at_the_limit_is_not_over', async () => {
    await renderNewEntry()

    type(textArea(), '🎉'.repeat(2000))

    expect(counterOf('entry-text')).toBe('2,000 / 2,000')
    expect(counterIsOver('entry-text')).toBe(false)
    expect(suggestButton().disabled).toBe(false)
  })

  it('test_fr_e2_past_the_limit_is_not_cut_and_shows_the_error_state', async () => {
    const user = userEvent.setup()
    await renderNewEntry()
    openFold()

    type(textArea(), 'a'.repeat(1990))
    await user.click(textArea())
    await user.paste('b'.repeat(115))
    type(resultInput(), 'r'.repeat(501))

    expect(textArea().value).toHaveLength(2105)
    expect(textArea().hasAttribute('maxlength')).toBe(false)
    expect(counterOf('entry-text')).toBe('2,105 / 2,000')
    expect(counterIsOver('entry-text')).toBe(true)
    expect(textArea().getAttribute('aria-invalid')).toBe('true')
    expect(counterOf('entry-result')).toBe('501 / 500')
    expect(resultInput().getAttribute('aria-invalid')).toBe('true')
    // No message until Save.
    expect(messagesOf('entry-text')).toEqual([])
  })

  it('test_fr_e2_counter_goes_when_the_text_is_back_under_80_percent', async () => {
    await renderNewEntry()

    type(textArea(), 'a'.repeat(1700))
    type(textArea(), 'a'.repeat(100))

    expect(counterOf('entry-text')).toBeNull()
  })
})

describe('saving over a limit (FR-E2)', () => {
  it('test_fr_e2_text_over_2000_characters_is_not_sent', async () => {
    await renderNewEntry()
    fillRequired('a'.repeat(2001))

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-text')).toEqual([TEXT_TOO_LONG])
    expect(document.activeElement).toBe(textArea())

    // The message goes once the text is within the limit, and the entry saves.
    type(textArea(), 'a'.repeat(2000))
    expect(messagesOf('entry-text')).toEqual([])
    await save()
    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0]?.[0].text).toBe('a'.repeat(2000))
  })

  it('test_fr_e2_result_over_500_characters_opens_the_fold_and_is_not_sent', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    type(resultInput(), 'r'.repeat(501))
    fireEvent.click(foldButton())
    expect(foldButton().getAttribute('aria-expanded')).toBe('false')

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(messagesOf('entry-result')).toEqual([RESULT_TOO_LONG])
    expect(document.activeElement).toBe(resultInput())

    type(resultInput(), 'r'.repeat(500))
    expect(messagesOf('entry-result')).toEqual([])
    await save()
    expect(createEntry.mock.calls[0]?.[0].result_impact).toBe('r'.repeat(500))
  })

  it('test_fr_e2_several_problems_show_every_message_and_focus_the_first', async () => {
    await renderNewEntry()
    type(textArea(), 'a'.repeat(2001))
    openFold()
    type(resultInput(), 'r'.repeat(501))

    await save()

    expect(messagesOf('entry-text')).toEqual([TEXT_TOO_LONG])
    expect(messagesOf('entry-category')).toEqual(['Choose a category, then save.'])
    expect(messagesOf('entry-result')).toEqual([RESULT_TOO_LONG])
    expect(document.activeElement).toBe(textArea())
  })

  it('test_fr_e2_entry_at_every_limit_is_sent_exactly', async () => {
    await renderNewEntry()
    fillRequired('🎉'.repeat(2000))
    openFold()
    type(resultInput(), '🎉'.repeat(500))
    for (const name of TEN_TAGS.slice(0, 9)) {
      addTag(name)
    }
    type(tagInput(), `  ${'t'.repeat(40)}  `)

    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    const body = createEntry.mock.calls[0]?.[0]
    expect(body?.text).toBe('🎉'.repeat(2000))
    expect(body?.result_impact).toBe('🎉'.repeat(500))
    expect(body?.tags).toEqual([...TEN_TAGS.slice(0, 9), 't'.repeat(40)])
  })

  it('test_fr_e2_saved_form_has_no_counter_or_messages', async () => {
    await renderNewEntry()
    fillRequired('a'.repeat(1700))
    expect(counterOf('entry-text')).toBe('1,700 / 2,000')

    await save()

    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(textArea().value).toBe('')
    expect(counterOf('entry-text')).toBeNull()
    expect(suggestHint()).toBeNull()
  })
})

describe('the suggest button (FR-S1)', () => {
  it('test_fr_s1_suggest_is_disabled_over_2000_characters_with_a_hint', async () => {
    await renderNewEntry()
    type(textArea(), 'a'.repeat(2001))

    expect(suggestButton().disabled).toBe(true)
    expect(suggestHint()?.textContent).toBe(SUGGEST_HINT)
    expect(suggestHint()?.getAttribute('role')).toBeNull()
    expect(suggestButton().getAttribute('aria-describedby')).toBe('entry-suggest-hint')
    fireEvent.click(suggestButton())
    expect(suggest).not.toHaveBeenCalled()

    type(textArea(), 'a'.repeat(2000))
    expect(suggestButton().disabled).toBe(false)
    expect(suggestHint()).toBeNull()
    expect(suggestButton().getAttribute('aria-describedby')).toBeNull()
  })

  it('test_fr_s1_empty_text_disables_suggest_without_a_hint', async () => {
    await renderNewEntry()

    expect(suggestButton().disabled).toBe(true)
    expect(suggestHint()).toBeNull()
  })

  it('test_fr_s2_a_suggestion_adds_tags_only_until_there_are_10', async () => {
    suggest.mockResolvedValue({ category: 'Learning', tags: ['One', 'Two', 'Three'] })
    await renderNewEntry()
    fillRequired()
    openFold()
    for (const name of TEN_TAGS.slice(0, 8)) {
      addTag(name)
    }

    await act(async () => {
      fireEvent.click(suggestButton())
    })

    expect(addedTags()).toEqual([...TEN_TAGS.slice(0, 8), 'One', 'Two'])
    // That feedback is #86: no tag message here.
    expect(messagesOf('entry-tags')).toEqual([])
  })
})

describe('tag limits (FR-E2)', () => {
  it('test_fr_e2_tag_over_40_characters_by_enter_is_not_added', async () => {
    await renderNewEntry()
    openFold()

    addTag(` ${LONG_TAG} `)

    expect(addedTags()).toEqual([])
    expect(tagInput().value).toBe(LONG_TAG)
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG])
    expect(tagInput().getAttribute('aria-invalid')).toBe('true')
  })

  it('test_fr_e2_tag_of_40_characters_after_trimming_is_added', async () => {
    await renderNewEntry()
    openFold()

    addTag(`   ${'t'.repeat(40)}   `)

    expect(addedTags()).toEqual(['t'.repeat(40)])
    expect(messagesOf('entry-tags')).toEqual([])
  })

  it('test_fr_e2_tag_over_40_characters_by_comma_is_not_added', async () => {
    await renderNewEntry()
    openFold()

    type(tagInput(), `Go,${LONG_TAG},`)

    expect(addedTags()).toEqual(['Go'])
    expect(tagInput().value).toBe(LONG_TAG)
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG])
  })

  it('test_fr_e2_an_11th_tag_is_not_added', async () => {
    await renderNewEntry()
    openFold()
    for (const name of TEN_TAGS) {
      addTag(name)
    }

    addTag('Eleven')

    expect(addedTags()).toEqual(TEN_TAGS)
    expect(tagInput().value).toBe('Eleven')
    expect(messagesOf('entry-tags')).toEqual([TOO_MANY_TAGS])
  })

  it('test_fr_e2_paste_adds_the_names_that_fit_and_keeps_the_others', async () => {
    const user = userEvent.setup()
    await renderNewEntry()
    openFold()
    for (const name of TEN_TAGS.slice(0, 8)) {
      addTag(name)
    }

    await user.click(tagInput())
    await user.paste(`a, ${LONG_TAG}, b, c, d`)

    expect(addedTags()).toEqual([...TEN_TAGS.slice(0, 8), 'a', 'b'])
    expect(tagInput().value).toBe(`${LONG_TAG}, c, d`)
    // Both messages, in this order.
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG, TOO_MANY_TAGS])
  })

  it('test_fr_e2_tag_messages_go_once_they_no_longer_apply', async () => {
    const user = userEvent.setup()
    await renderNewEntry()
    openFold()
    for (const name of TEN_TAGS) {
      addTag(name)
    }
    await user.click(tagInput())
    await user.paste(`${LONG_TAG}, Eleven`)
    expect(tagInput().value).toBe(`${LONG_TAG}, Eleven`)
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG, TOO_MANY_TAGS])

    // The long name is gone from the input, but a name is still there: 10-tag message only.
    type(tagInput(), 'Eleven')
    expect(messagesOf('entry-tags')).toEqual([TOO_MANY_TAGS])
    // The input is empty with 10 tags: no message, and none comes back on typing.
    type(tagInput(), '')
    expect(messagesOf('entry-tags')).toEqual([])
    type(tagInput(), LONG_TAG)
    expect(messagesOf('entry-tags')).toEqual([])
  })

  it('test_fr_e2_removing_a_tag_clears_the_10_tag_message', async () => {
    await renderNewEntry()
    openFold()
    for (const name of TEN_TAGS) {
      addTag(name)
    }
    addTag('Eleven')

    fireEvent.click(screen.getByRole('button', { name: 'Remove Tag 0' }))

    expect(messagesOf('entry-tags')).toEqual([])
    key(tagInput(), 'Enter')
    expect(addedTags()).toEqual([...TEN_TAGS.slice(1), 'Eleven'])
  })

  it('test_fr_e2_save_with_a_long_name_in_the_tag_input_sends_nothing', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    type(tagInput(), LONG_TAG)
    fireEvent.click(foldButton())

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG])
    expect(tagInput().value).toBe(LONG_TAG)
    expect(document.activeElement).toBe(tagInput())
  })

  it('test_fr_e2_save_with_an_11th_name_in_the_tag_input_sends_nothing', async () => {
    await renderNewEntry()
    fillRequired()
    openFold()
    for (const name of TEN_TAGS) {
      addTag(name)
    }
    type(tagInput(), 'Eleven')

    await save()

    expect(createEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-tags')).toEqual([TOO_MANY_TAGS])
    expect(tagInput().value).toBe('Eleven')
    expect(document.activeElement).toBe(tagInput())
  })

  it('test_fr_e2_server_tag_error_still_shows_check_your_tags', async () => {
    createEntry.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [
        { field: 'tags', reason: 'An entry can have at most 10 tags.' },
      ]),
    )
    await renderNewEntry()
    fillRequired()

    await save()

    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(messagesOf('entry-tags')).toEqual(['Check your tags, then save.'])
    expect(document.body.textContent).not.toContain('at most 10 tags')
  })
})

describe('entries saved before the limits (FR-E2, FR-E4)', () => {
  it('test_fr_e4_over_long_text_and_result_show_the_over_limit_counter_and_save_once_shortened', async () => {
    getEntry.mockResolvedValue(storedEntry({ text: 'a'.repeat(2100), result_impact: 'r'.repeat(600) }))
    await renderEdit()

    expect(counterOf('entry-text')).toBe('2,100 / 2,000')
    expect(counterIsOver('entry-text')).toBe(true)
    expect(textArea().getAttribute('aria-invalid')).toBe('true')
    expect(foldButton().getAttribute('aria-expanded')).toBe('true')
    expect(counterOf('entry-result')).toBe('600 / 500')

    await save()
    expect(updateEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-text')).toEqual([TEXT_TOO_LONG])
    expect(messagesOf('entry-result')).toEqual([RESULT_TOO_LONG])
    expect(document.activeElement).toBe(textArea())

    type(textArea(), 'a'.repeat(2000))
    type(resultInput(), 'r'.repeat(500))
    await save()
    expect(updateEntry).toHaveBeenCalledTimes(1)
  })

  it('test_fr_e4_too_many_or_too_long_tags_show_their_messages_on_save', async () => {
    const legacyTags = [...TEN_TAGS, 'Extra', 'L'.repeat(50)]
    getEntry.mockResolvedValue(storedEntry({ tags: legacyTags }))
    await renderEdit()

    // Nothing shows until Save.
    expect(addedTags()).toEqual(legacyTags)
    expect(messagesOf('entry-tags')).toEqual([])

    await save()
    expect(updateEntry).not.toHaveBeenCalled()
    expect(messagesOf('entry-tags')).toEqual([TAG_TOO_LONG, TOO_MANY_TAGS])
    expect(document.activeElement).toBe(tagInput())

    fireEvent.click(screen.getByRole('button', { name: `Remove ${'L'.repeat(50)}` }))
    expect(messagesOf('entry-tags')).toEqual([TOO_MANY_TAGS])
    fireEvent.click(screen.getByRole('button', { name: 'Remove Extra' }))
    expect(messagesOf('entry-tags')).toEqual([])

    await save()
    expect(updateEntry).toHaveBeenCalledTimes(1)
    expect(updateEntry.mock.calls[0]?.[1].tags).toEqual(TEN_TAGS)
  })
})
