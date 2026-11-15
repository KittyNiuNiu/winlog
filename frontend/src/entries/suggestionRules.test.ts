import { describe, expect, it } from 'vitest'
import { AiUnavailableError, LimitReachedError, NetworkError, UnknownError, ValidationError } from '../api/index.ts'
import type { Category, Suggestion } from '../api/index.ts'
import {
  GLOBAL_LIMIT_MESSAGE,
  NO_MARKS,
  NO_NEW_SUGGESTIONS_MESSAGE,
  SUGGESTED_TAGS_LEFT_OUT_MESSAGE,
  SUGGESTIONS_UNAVAILABLE_MESSAGE,
  USER_SUGGESTION_LIMIT_MESSAGE,
  answerNoticeOf,
  applySuggestion,
  discardSuggestions,
  hasSuggestions,
  marksAfterCategoryChoice,
  marksAfterTagChange,
  suggestedCategoryHint,
  suggestionNoticeOf,
} from './suggestions.ts'

// The rules for applying and discarding AI suggestions (#28, FR-S2, FR-S3).

describe('applySuggestion', () => {
  it('test_fr_s2_fills_an_empty_category_and_marks_it', () => {
    const result = applySuggestion({ values: { category: null, tags: [] }, marks: NO_MARKS }, {
      category: 'Learning',
      tags: [],
    })

    expect(result.values.category).toBe('Learning')
    expect(result.marks).toEqual({ category: 'Learning', hint: null, tags: [] })
    expect(result.addedTags).toBe(false)
  })

  it('test_fr_s2_chosen_category_not_overridden_and_gets_the_hint', () => {
    const result = applySuggestion({ values: { category: 'Feedback', tags: [] }, marks: NO_MARKS }, {
      category: 'Learning',
      tags: [],
    })

    expect(result.values.category).toBe('Feedback')
    expect(result.marks.hint).toBe('Learning')
    expect(result.marks.category).toBeNull()
  })

  it('test_fr_s2_the_same_category_gives_no_mark_and_no_hint', () => {
    const result = applySuggestion({ values: { category: 'Learning', tags: [] }, marks: NO_MARKS }, {
      category: 'Learning',
      tags: [],
    })

    expect(result.marks).toEqual(NO_MARKS)
    expect(hasSuggestions(result.marks)).toBe(false)
  })

  it('test_fr_s2_adds_new_tags_at_the_end_without_duplicates_ignoring_case', () => {
    const result = applySuggestion(
      { values: { category: 'Learning', tags: ['python', 'ci'] }, marks: NO_MARKS },
      { category: 'Learning', tags: ['Python', 'Mock tag', 'mock TAG', 'CI', 'Rust'] },
    )

    expect(result.values.tags).toEqual(['python', 'ci', 'Mock tag', 'Rust'])
    expect(result.marks.tags).toEqual(['Mock tag', 'Rust'])
    expect(result.addedTags).toBe(true)
  })

  it('test_fr_s2_asking_again_replaces_the_earlier_suggestions', () => {
    const first = applySuggestion({ values: { category: null, tags: ['mine'] }, marks: NO_MARKS }, {
      category: 'Learning',
      tags: ['Python'],
    })

    const second = applySuggestion(first, { category: 'Side project', tags: ['Rust'] })

    expect(second.values).toEqual({ category: 'Side project', tags: ['mine', 'Rust'] })
    expect(second.marks).toEqual({ category: 'Side project', hint: null, tags: ['Rust'] })
  })

  it('test_fr_s2_keeps_other_fields_as_they_are', () => {
    const result = applySuggestion(
      { values: { text: 'Learned', category: null, tags: [], result: 'x' }, marks: NO_MARKS },
      { category: 'Learning', tags: [] },
    )

    expect(result.values).toEqual({ text: 'Learned', category: 'Learning', tags: [], result: 'x' })
  })
})

describe('discardSuggestions', () => {
  it('test_fr_s3_discard_suggestions_keeps_the_users_own_values', () => {
    const form = {
      values: { category: 'Learning' as const, tags: ['mine', 'Python', 'Rust'] },
      marks: { category: 'Learning' as const, hint: null, tags: ['Python', 'Rust'] },
    }

    expect(discardSuggestions(form)).toEqual({ values: { category: null, tags: ['mine'] }, marks: NO_MARKS })
  })

  it('test_fr_s3_discard_keeps_a_category_that_is_the_users_own', () => {
    const form = {
      values: { category: 'Feedback' as const, tags: [] },
      marks: { category: null, hint: 'Learning' as const, tags: [] },
    }

    expect(discardSuggestions(form)).toEqual({ values: { category: 'Feedback', tags: [] }, marks: NO_MARKS })
  })
})

describe('taking a suggestion over', () => {
  it('test_fr_s2_choosing_a_category_removes_the_mark_and_the_hint_once_it_is_the_same', () => {
    const marks = { category: null, hint: 'Learning' as const, tags: ['Rust'] }

    expect(marksAfterCategoryChoice(marks, 'Feedback')).toEqual(marks)
    expect(marksAfterCategoryChoice(marks, 'Learning')).toEqual({ category: null, hint: null, tags: ['Rust'] })
    expect(marksAfterCategoryChoice({ ...NO_MARKS, category: 'Learning' }, 'Learning')).toEqual(NO_MARKS)
  })

  it('test_fr_s2_a_typed_name_or_a_removed_tag_loses_its_mark', () => {
    const marks = { category: null, hint: null, tags: ['Python', 'Rust', 'Go'] }

    expect(marksAfterTagChange(marks, ['Python', 'Rust', 'Go'], [' rust '])).toEqual({ ...marks, tags: ['Python', 'Go'] })
    expect(marksAfterTagChange(marks, ['Python', 'Rust'], [])).toEqual({ ...marks, tags: ['Python', 'Rust'] })
    expect(marksAfterTagChange(marks, ['Python', 'Rust', 'Go'], ['other'])).toBe(marks)
  })
})

describe('texts', () => {
  it('test_fr_s2_hint_names_the_category', () => {
    expect(suggestedCategoryHint('Side project')).toBe('Suggested: Side project')
  })

  it.each([
    [new AiUnavailableError('timeout', 503), SUGGESTIONS_UNAVAILABLE_MESSAGE],
    [new LimitReachedError('x', 429, 'user_suggestions'), USER_SUGGESTION_LIMIT_MESSAGE],
    [new LimitReachedError('x', 429, 'global'), GLOBAL_LIMIT_MESSAGE],
    [new LimitReachedError('x', 429, null), SUGGESTIONS_UNAVAILABLE_MESSAGE],
    [new LimitReachedError('x', 429, 'user_summaries'), SUGGESTIONS_UNAVAILABLE_MESSAGE],
    [new NetworkError(), "Can't reach Winlog. Check your connection and try again."],
    [new ValidationError('x', 422, []), 'Something went wrong. Please try again.'],
    [new UnknownError('x', 500, 'internal_error'), 'Something went wrong. Please try again.'],
  ])('test_fr_s1_notice_for_%s', (error, message) => {
    expect(suggestionNoticeOf(error)).toBe(message)
  })
})

describe('the 10-tag limit (#43, FR-S2)', () => {
  it('test_fr_s2_a_suggestion_adds_tags_in_order_only_until_there_are_10', () => {
    const eight = Array.from({ length: 8 }, (_, index) => `Tag ${index}`)
    const result = applySuggestion(
      { values: { category: 'Learning', tags: eight }, marks: NO_MARKS },
      { category: 'Learning', tags: ['tag 0', 'One', 'Two', 'Three'] },
    )

    expect(result.values.tags).toEqual([...eight, 'One', 'Two'])
    expect(result.marks.tags).toEqual(['One', 'Two'])
    expect(result.addedTags).toBe(true)
  })

  it('test_fr_s2_a_suggestion_adds_no_tag_to_an_entry_with_10_or_more', () => {
    const eleven = Array.from({ length: 11 }, (_, index) => `Tag ${index}`)
    const result = applySuggestion(
      { values: { category: null, tags: eleven }, marks: NO_MARKS },
      { category: 'Learning', tags: ['One'] },
    )

    expect(result.values.tags).toEqual(eleven)
    expect(result.addedTags).toBe(false)
  })
})

describe('the notice an answer gives (#86, FR-S2)', () => {
  const NOTHING_NEW = 'No new suggestions for this text.'
  const LEFT_OUT = 'Up to 10 tags per entry, so not every suggested tag was added.'
  const EIGHT = Array.from({ length: 8 }, (_, index) => `Tag ${index}`)
  const TEN = Array.from({ length: 10 }, (_, index) => `Tag ${index}`)

  /** A form with only the user's own values: nothing suggested yet. */
  function own(category: Category | null, tags: string[] = []) {
    return { values: { category, tags }, marks: NO_MARKS }
  }

  it('test_fr_s2_the_two_answer_texts_word_for_word', () => {
    expect(NO_NEW_SUGGESTIONS_MESSAGE).toBe(NOTHING_NEW)
    // The number is TAGS_PER_ENTRY_MAX, as in the tag field's "Up to 10 tags per entry."
    expect(SUGGESTED_TAGS_LEFT_OUT_MESSAGE).toBe(LEFT_OUT)
  })

  it.each<[string, ReturnType<typeof own>, Suggestion]>([
    ['the chosen category and tags already on the entry, ignoring case', own('Learning', ['python', 'ci']), {
      category: 'Learning',
      tags: ['PYTHON', 'ci'],
    }],
    ['the chosen category and an empty tag list', own('Learning'), { category: 'Learning', tags: [] }],
    ['the entry\'s own category and tags (edit page)', own('Feedback', ['Leadership', 'incident']), {
      category: 'Feedback',
      tags: ['leadership', 'Incident'],
    }],
  ])('test_fr_s2_an_answer_with_nothing_new_gives_its_notice: %s', (_case, form, suggestion) => {
    expect(answerNoticeOf(form, suggestion)).toBe(NOTHING_NEW)
    // The answer is still applied by #28's rules: here it changes nothing.
    const applied = applySuggestion(form, suggestion)
    expect(applied.values).toEqual(form.values)
    expect(applied.marks).toEqual(NO_MARKS)
  })

  it.each<[string, ReturnType<typeof own>, Suggestion]>([
    ['an empty category filled', own(null, ['python']), { category: 'Learning', tags: ['Python'] }],
    ['a new hint', own('Feedback'), { category: 'Learning', tags: [] }],
    ['one new tag', own('Learning', ['python']), { category: 'Learning', tags: ['Python', 'Rust'] }],
  ])('test_fr_s2_an_answer_with_something_new_gives_no_notice: %s', (_case, form, suggestion) => {
    expect(answerNoticeOf(form, suggestion)).toBeNull()
  })

  it('test_fr_s2_tags_left_out_at_10_give_the_tag_limit_notice', () => {
    // 8 tags and 3 new ones: the first 2 are added, the third is left out.
    const eight = own('Learning', EIGHT)
    const answer: Suggestion = { category: 'Learning', tags: ['One', 'Two', 'Three'] }
    expect(applySuggestion(eight, answer)).toMatchObject({ addedTags: true, tagsLeftOut: true })
    expect(answerNoticeOf(eight, answer)).toBe(LEFT_OUT)

    // 10 tags and an empty category: no tag is added, the category is filled and marked.
    const ten = own(null, TEN)
    const applied = applySuggestion(ten, { category: 'Learning', tags: ['One'] })
    expect(applied.values).toEqual({ category: 'Learning', tags: TEN })
    expect(applied.marks).toEqual({ category: 'Learning', hint: null, tags: [] })
    expect(answerNoticeOf(ten, { category: 'Learning', tags: ['One'] })).toBe(LEFT_OUT)
  })

  it('test_fr_s2_the_tag_limit_notice_wins_over_nothing_new', () => {
    // Nothing else is new, so both texts would apply: only the tag-limit text shows.
    expect(answerNoticeOf(own('Learning', TEN), { category: 'Learning', tags: ['tag 0', 'One'] })).toBe(LEFT_OUT)
    // An entry saved before the limits, with more than 10 tags.
    const eleven = [...TEN, 'Tag 10']
    expect(answerNoticeOf(own('Feedback', eleven), { category: 'Learning', tags: ['One'] })).toBe(LEFT_OUT)
  })

  it('test_fr_s2_at_10_tags_suggested_tags_already_on_the_entry_are_not_left_out', () => {
    const ten = own('Learning', TEN)
    const answer: Suggestion = { category: 'Learning', tags: ['TAG 0', 'tag 9'] }

    expect(applySuggestion(ten, answer).tagsLeftOut).toBe(false)
    expect(answerNoticeOf(ten, answer)).toBe(NOTHING_NEW)
    // Something else new: no notice at all.
    expect(answerNoticeOf(own('Feedback', TEN), answer)).toBeNull()
  })

  it('test_fr_s2_asking_again_with_the_same_answer_gives_the_nothing_new_notice', () => {
    const answer: Suggestion = { category: 'Learning', tags: ['Python', 'Mock tag'] }
    const first = applySuggestion(own(null, ['mine']), answer)
    expect(answerNoticeOf(own(null, ['mine']), answer)).toBeNull()

    expect(answerNoticeOf(first, answer)).toBe(NOTHING_NEW)
    // The same suggestions come back as they were.
    expect(applySuggestion(first, answer).marks).toEqual(first.marks)
    // Tag names ignore case.
    expect(answerNoticeOf(first, { category: 'Learning', tags: ['python', 'MOCK TAG'] })).toBe(NOTHING_NEW)

    // The same hint again.
    const hinted = applySuggestion(own('Feedback'), { category: 'Learning', tags: [] })
    expect(answerNoticeOf(hinted, { category: 'Learning', tags: [] })).toBe(NOTHING_NEW)
  })

  it('test_fr_s2_asking_again_when_the_new_answer_adds_nothing_gives_the_nothing_new_notice', () => {
    // The earlier hint and tag go first, then nothing new is shown.
    const first = applySuggestion(own('Feedback', ['mine']), { category: 'Learning', tags: ['Python'] })
    const answer: Suggestion = { category: 'Feedback', tags: ['MINE'] }
    expect(applySuggestion(first, answer)).toMatchObject({
      values: { category: 'Feedback', tags: ['mine'] },
      marks: NO_MARKS,
    })
    expect(answerNoticeOf(first, answer)).toBe(NOTHING_NEW)

    // Fewer tags than before, and the same marked category: nothing new either.
    const marked = applySuggestion(own(null), { category: 'Learning', tags: ['Python', 'Rust'] })
    expect(answerNoticeOf(marked, { category: 'Learning', tags: ['rust'] })).toBe(NOTHING_NEW)
    // Another category or one more tag is new.
    expect(answerNoticeOf(marked, { category: 'Side project', tags: [] })).toBeNull()
    expect(answerNoticeOf(marked, { category: 'Learning', tags: ['Python', 'Rust', 'Go'] })).toBeNull()
  })

  it('test_fr_s2_asking_again_with_8_own_tags_and_2_earlier_suggested_tags', () => {
    const first = applySuggestion(own('Learning', EIGHT), { category: 'Learning', tags: ['One', 'Two'] })
    expect(first.marks.tags).toEqual(['One', 'Two'])

    // The 2 earlier ones are removed first, so 2 new tags fit.
    expect(answerNoticeOf(first, { category: 'Learning', tags: ['Three', 'Four'] })).toBeNull()
    // A third new tag is left out.
    expect(answerNoticeOf(first, { category: 'Learning', tags: ['Three', 'Four', 'Five'] })).toBe(LEFT_OUT)
  })

  it('test_fr_s2_the_notice_follows_the_form_as_it_is_when_the_answer_arrives', () => {
    const answer: Suggestion = { category: 'Learning', tags: ['Python', 'Rust'] }
    const first = applySuggestion(own(null), answer)

    // The user removed a suggested tag meanwhile: it comes back, which is new.
    const removed = { values: { ...first.values, tags: ['Python'] }, marks: { ...first.marks, tags: ['Python'] } }
    expect(answerNoticeOf(removed, answer)).toBeNull()

    // The user took the category over meanwhile: the same answer shows no mark and no hint.
    const takenOver = { values: first.values, marks: marksAfterCategoryChoice(first.marks, 'Learning') }
    expect(answerNoticeOf(takenOver, answer)).toBe(NOTHING_NEW)
  })
})
