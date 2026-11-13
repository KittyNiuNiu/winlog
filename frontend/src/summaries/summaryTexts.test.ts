import { afterEach, describe, expect, it, vi } from 'vitest'
import { NetworkError, NotFoundError, UnknownError } from '../api/index.ts'
import * as editor from '../components/summaryEditor.ts'
import * as draft from '../review/summaryDraft.ts'
import { summaryDeletedNoticeOf, summaryDeletedState } from './summaryDeletedNotice.ts'
import { createdDateParts, createdDateText, createdLine, localDateOf, previewText } from './summaryTexts.ts'

// The helpers of the summaries pages (#33). Tests run in Sydney (vite.config.ts).

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('creation dates (FR-R4)', () => {
  it('test_fr_r4_creation_date_is_the_local_day_near_midnight_utc', () => {
    expect(localDateOf('2026-11-12T22:30:00Z')).toBe('2026-11-13')
    expect(createdDateText('2026-11-12T22:30:00Z')).toBe('13 Nov 2026')
    expect(createdLine('2026-11-12T22:30:00Z')).toBe('Created 13 Nov 2026')
    expect(createdDateParts('2026-11-12T22:30:00Z')).toEqual({ dayMonth: '13 Nov', year: '2026' })
  })

  it('test_fr_r4_creation_date_behind_utc', () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    expect(createdDateText('2026-01-01T03:00:00Z')).toBe('31 Dec 2025')
    expect(createdDateParts('2026-01-01T03:00:00Z')).toEqual({ dayMonth: '31 Dec', year: '2025' })
  })

  it('test_fr_r4_a_text_that_is_no_timestamp_is_shown_as_it_is', () => {
    expect(createdDateText('not a date')).toBe('not a date')
    expect(createdDateParts('not a date')).toEqual({ dayMonth: 'not a date', year: '' })
  })
})

describe('the list preview (FR-R4)', () => {
  it('test_fr_r4_preview_turns_line_breaks_into_spaces', () => {
    expect(previewText('  Mock summary\n\nLed the review.\r\n\tShipped.  ')).toBe('Mock summary Led the review. Shipped.')
  })

  it('test_fr_r4_preview_keeps_a_text_of_240_characters', () => {
    const text = 'a'.repeat(240)
    expect(previewText(text)).toBe(text)
  })

  it('test_fr_r4_preview_cuts_a_longer_text_to_240_characters_and_an_ellipsis', () => {
    expect(previewText('a'.repeat(241))).toBe(`${'a'.repeat(240)}…`)
    // No space before the ellipsis.
    expect(previewText(`${'a'.repeat(239)} bcd`)).toBe(`${'a'.repeat(239)}…`)
  })
})

describe('the one-time notice after a delete (FR-R5)', () => {
  it('test_fr_r5_notice_round_trips_through_the_navigation_state', () => {
    expect(summaryDeletedNoticeOf(summaryDeletedState('deleted'))).toBe('deleted')
    expect(summaryDeletedNoticeOf(summaryDeletedState('gone'))).toBe('gone')
  })

  it.each([null, undefined, 'deleted', {}, { summaryDeleted: true }, { entrySaved: true }])(
    'test_fr_r5_no_notice_for_other_state_%#',
    (state) => {
      expect(summaryDeletedNoticeOf(state)).toBeNull()
    },
  )
})

describe('texts shared with the review page panel (#32)', () => {
  it('test_fr_r5_panel_and_page_use_the_same_texts', () => {
    expect(draft.SUMMARY_FIELD_LABEL).toBe(editor.SUMMARY_FIELD_LABEL)
    expect(draft.SAVE_SUMMARY_LABEL).toBe(editor.SAVE_SUMMARY_LABEL)
    expect(draft.SAVING_LABEL).toBe(editor.SAVING_LABEL)
    expect(draft.SUMMARY_SAVED_TEXT).toBe(editor.SUMMARY_SAVED_TEXT)
    expect(draft.EMPTY_SUMMARY_TEXT).toBe(editor.EMPTY_SUMMARY_TEXT)
    expect(draft.SUMMARY_GONE_MESSAGE).toBe(editor.SUMMARY_GONE_MESSAGE)
    expect(draft.sourceLine).toBe(editor.sourceLine)
    expect(draft.saveErrorOf).toBe(editor.saveErrorOf)
  })

  it('test_fr_r5_save_errors_never_show_the_server_message', () => {
    expect(editor.saveErrorOf(new NotFoundError('server text', 404))).toBe(
      "This summary no longer exists, so your changes can't be saved.",
    )
    expect(editor.saveErrorOf(new NetworkError())).toBe("Can't reach Winlog. Check your connection and try again.")
    expect(editor.saveErrorOf(new UnknownError('server text', 500, 'internal_error'))).toBe(
      'Something went wrong. Please try again.',
    )
  })
})
