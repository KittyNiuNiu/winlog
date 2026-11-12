import { describe, expect, it } from 'vitest'
import { AiUnavailableError, LimitReachedError, NetworkError, UnknownError, ValidationError } from '../api/index.ts'
import {
  GLOBAL_LIMIT_MESSAGE,
  NO_MARKS,
  SUGGESTIONS_UNAVAILABLE_MESSAGE,
  USER_SUGGESTION_LIMIT_MESSAGE,
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
