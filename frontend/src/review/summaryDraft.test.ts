import { describe, expect, it } from 'vitest'
import {
  AiUnavailableError,
  LimitReachedError,
  NetworkError,
  NoMatchingEntriesError,
  NotFoundError,
  UnknownError,
  ValidationError,
} from '../api/index.ts'
import { GLOBAL_LIMIT_MESSAGE } from '../components/aiTexts.ts'
import { summaryFilterText } from '../components/summaryFilterText.ts'
import { GLOBAL_LIMIT_MESSAGE as SUGGESTIONS_GLOBAL_LIMIT_MESSAGE } from '../entries/suggestions.ts'
import { NO_FILTER, type ReviewFilter } from './reviewFilter.ts'
import {
  DATE_ORDER_HINT,
  NEED_DATES_HINT,
  NOTHING_TO_SUMMARISE_HINT,
  NO_MATCHING_ENTRIES_MESSAGE,
  SUMMARY_GONE_MESSAGE,
  SUMMARY_UNAVAILABLE_MESSAGE,
  USER_SUMMARY_LIMIT_MESSAGE,
  draftAgainLine,
  draftAvailability,
  draftLine,
  draftNoticeOf,
  saveErrorOf,
  summaryRequest,
} from './summaryDraft.ts'

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'

const PERIOD: ReviewFilter = { ...NO_FILTER, startDate: '2026-01-01', endDate: '2026-06-30' }

describe('when drafting is possible (FR-R3)', () => {
  it('test_fr_r3_rules_in_order_of_priority', () => {
    // Missing dates come first, even while entries load or none match.
    expect(draftAvailability(NO_FILTER, 3)).toEqual({ kind: 'hint', hint: NEED_DATES_HINT })
    expect(draftAvailability({ ...PERIOD, startDate: null }, null)).toEqual({ kind: 'hint', hint: NEED_DATES_HINT })
    expect(draftAvailability({ ...PERIOD, endDate: null }, 0)).toEqual({ kind: 'hint', hint: NEED_DATES_HINT })
    // Then the date order.
    const reversed = { ...PERIOD, startDate: '2026-07-01' }
    expect(draftAvailability(reversed, null)).toEqual({ kind: 'hint', hint: DATE_ORDER_HINT })
    // Then loading or a failed load, with no hint of its own.
    expect(draftAvailability(PERIOD, null)).toEqual({ kind: 'waiting' })
    // Then no entries.
    expect(draftAvailability(PERIOD, 0)).toEqual({ kind: 'hint', hint: NOTHING_TO_SUMMARISE_HINT })
    expect(draftAvailability(PERIOD, 12)).toEqual({ kind: 'ready', count: 12 })
    // The same day for start and end is fine.
    expect(draftAvailability({ ...PERIOD, endDate: '2026-01-01' }, 1)).toEqual({ kind: 'ready', count: 1 })
  })

  it('test_fr_r3_entry_count_lines', () => {
    expect(draftLine(12)).toBe('Draft a summary of the 12 entries shown.')
    expect(draftLine(1)).toBe('Draft a summary of the 1 entry shown.')
    expect(draftAgainLine(12)).toBe('Draft a new summary of the 12 entries shown. This draft stays in Summaries.')
    expect(draftAgainLine(1)).toBe('Draft a new summary of the 1 entry shown. This draft stays in Summaries.')
  })

  it('test_fr_r3_request_sends_categories_and_tags_only_when_selected', () => {
    expect(summaryRequest(PERIOD)).toEqual({ period_start: '2026-01-01', period_end: '2026-06-30' })
    expect(
      summaryRequest({ ...PERIOD, categories: ['Achievement', 'Feedback'], tags: ['python', 'Leadership'] }),
    ).toEqual({
      period_start: '2026-01-01',
      period_end: '2026-06-30',
      categories: ['Achievement', 'Feedback'],
      tags: ['python', 'Leadership'],
    })
    expect(summaryRequest({ ...PERIOD, startDate: null })).toBeNull()
  })
})

describe('the filter description (FR-R3)', () => {
  it('test_fr_r3_period_categories_in_fixed_order_and_tags', () => {
    expect(summaryFilterText({ period_start: '2026-01-01', period_end: '2026-06-30' })).toBe(
      '1 Jan 2026 – 30 Jun 2026 · All categories · All tags',
    )
    expect(
      summaryFilterText({
        period_start: '2026-01-01',
        period_end: '2026-06-30',
        categories: ['Learning', 'Achievement'],
        tags: [],
      }),
    ).toBe('1 Jan 2026 – 30 Jun 2026 · Achievement, Learning · All tags')
    expect(
      summaryFilterText({
        period_start: '2025-12-31',
        period_end: '2026-01-01',
        categories: [],
        tags: ['python', 'Leadership'],
      }),
    ).toBe('31 Dec 2025 – 1 Jan 2026 · All categories · python, Leadership')
  })
})

describe('the notices (FR-R3, FR-R5, §7.4, §8)', () => {
  it.each([
    [new NoMatchingEntriesError('server text', 422), NO_MATCHING_ENTRIES_MESSAGE],
    [new AiUnavailableError('server text', 503), SUMMARY_UNAVAILABLE_MESSAGE],
    [new LimitReachedError('server text', 429, 'user_summaries'), USER_SUMMARY_LIMIT_MESSAGE],
    [new LimitReachedError('server text', 429, 'global'), GLOBAL_LIMIT_MESSAGE],
    [new LimitReachedError('server text', 429, 'user_suggestions'), SUMMARY_UNAVAILABLE_MESSAGE],
    [new LimitReachedError('server text', 429, null), SUMMARY_UNAVAILABLE_MESSAGE],
    [new NetworkError(), NETWORK_MESSAGE],
    [new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
    [new ValidationError('server text', 422, []), GENERIC_MESSAGE],
  ])('test_fr_r3_draft_notice_for_%s', (error, text) => {
    expect(draftNoticeOf(error)).toBe(text)
  })

  it('test_fr_r3_global_limit_text_is_the_same_as_for_suggestions', () => {
    expect(GLOBAL_LIMIT_MESSAGE).toBe("Winlog has reached today's AI limit for everyone. Try again after midnight UTC.")
    expect(SUGGESTIONS_GLOBAL_LIMIT_MESSAGE).toBe(GLOBAL_LIMIT_MESSAGE)
  })

  it('test_fr_r5_save_error_texts', () => {
    expect(saveErrorOf(new NotFoundError('server text', 404))).toBe(SUMMARY_GONE_MESSAGE)
    expect(SUMMARY_GONE_MESSAGE).toBe("This summary no longer exists, so your changes can't be saved.")
    expect(saveErrorOf(new NetworkError())).toBe(NETWORK_MESSAGE)
    expect(saveErrorOf(new UnknownError('server text', 500, null))).toBe(GENERIC_MESSAGE)
  })
})
