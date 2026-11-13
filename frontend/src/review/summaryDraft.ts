// The summary panel on the review page (FR-R3 to FR-R5, #32 and its design note): its
// texts, when drafting is possible, the request for the filter shown, and the notice for a
// failed draft. The server's own message is never shown.
import {
  AiUnavailableError,
  LimitReachedError,
  NoMatchingEntriesError,
  NotFoundError,
  type SummaryFilter,
} from '../api/index.ts'
import { unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { GLOBAL_LIMIT_MESSAGE } from '../components/aiTexts.ts'
import { startAfterEnd, type ReviewFilter } from './reviewFilter.ts'

export const SUMMARY_TITLE = 'Summary'
export const DRAFT_LABEL = 'Draft summary'
export const DRAFT_AGAIN_LABEL = 'Draft again'
export const DRAFTING_LABEL = 'Drafting…'
export const SAVE_SUMMARY_LABEL = 'Save summary'
export const SAVING_LABEL = 'Saving…'
export const SUMMARY_FIELD_LABEL = 'Summary text'

export const DRAFTING_TEXT = 'Writing your summary… This can take up to a minute.'
export const DRAFT_NOTE = 'This draft is saved in Summaries. Edit it as you like, then save your changes.'
export const SUMMARY_SAVED_TEXT = 'Summary saved.'
export const EMPTY_SUMMARY_TEXT = 'Write your summary, then save.'
export const SUMMARY_GONE_MESSAGE = "This summary no longer exists, so your changes can't be saved."

export const NEED_DATES_HINT = 'Choose a start and end date to draft a summary.'
export const DATE_ORDER_HINT = 'Choose a start date on or before the end date to draft a summary.'
export const NOTHING_TO_SUMMARISE_HINT = "No entries match these filters, so there's nothing to summarise."

export const NO_MATCHING_ENTRIES_MESSAGE = 'No entries match these filters, so no summary was created.'
export const SUMMARY_UNAVAILABLE_MESSAGE = "The summary couldn't be written right now. Please try again later."
export const USER_SUMMARY_LIMIT_MESSAGE = "You've used today's summaries. They're available again after midnight UTC."

function entriesShown(count: number): string {
  return `${count} ${count === 1 ? 'entry' : 'entries'} shown`
}

/** The line under "Draft summary": "Draft a summary of the 12 entries shown." */
export function draftLine(count: number): string {
  return `Draft a summary of the ${entriesShown(count)}.`
}

/** The line under "Draft again", which keeps the draft shown in Summaries. */
export function draftAgainLine(count: number): string {
  return `Draft a new summary of the ${entriesShown(count)}. This draft stays in Summaries.`
}

/** The panel's source line: which entries the draft is from. */
export function sourceLine(filterText: string): string {
  return `Entries from ${filterText}`
}

/** Whether "Draft summary" and "Draft again" can be used for the filter shown. */
export type DraftAvailability =
  | { kind: 'ready'; count: number }
  /** Disabled, with a hint that says why. */
  | { kind: 'hint'; hint: string }
  /** Disabled while the entries load or after they failed; the page itself says why. */
  | { kind: 'waiting' }

/**
 * Drafting is possible with both dates set, in order, and at least one entry shown. The
 * first rule that applies decides, so the hint does not flicker while entries reload.
 *
 * @param count The number of entries shown for the current filter, or null while they
 *   load or after they failed to load.
 */
export function draftAvailability(filter: ReviewFilter, count: number | null): DraftAvailability {
  if (filter.startDate === null || filter.endDate === null) {
    return { kind: 'hint', hint: NEED_DATES_HINT }
  }
  if (startAfterEnd(filter)) {
    return { kind: 'hint', hint: DATE_ORDER_HINT }
  }
  if (count === null) {
    return { kind: 'waiting' }
  }
  if (count === 0) {
    return { kind: 'hint', hint: NOTHING_TO_SUMMARISE_HINT }
  }
  return { kind: 'ready', count }
}

/**
 * The `POST /summaries` body for the filter shown: the period, and the categories and tags
 * only when some are selected. Null when a date is missing.
 */
export function summaryRequest(filter: ReviewFilter): SummaryFilter | null {
  if (filter.startDate === null || filter.endDate === null) {
    return null
  }
  const body: SummaryFilter = { period_start: filter.startDate, period_end: filter.endDate }
  if (filter.categories.length > 0) {
    body.categories = [...filter.categories]
  }
  if (filter.tags.length > 0) {
    body.tags = [...filter.tags]
  }
  return body
}

/** The notice for a failed draft. */
export function draftNoticeOf(error: unknown): string {
  if (error instanceof NoMatchingEntriesError) {
    return NO_MATCHING_ENTRIES_MESSAGE
  }
  if (error instanceof LimitReachedError) {
    if (error.limit === 'user_summaries') {
      return USER_SUMMARY_LIMIT_MESSAGE
    }
    if (error.limit === 'global') {
      return GLOBAL_LIMIT_MESSAGE
    }
    // No limit named, or one that is not about summaries (as #28 does for suggestions).
    return SUMMARY_UNAVAILABLE_MESSAGE
  }
  if (error instanceof AiUnavailableError) {
    return SUMMARY_UNAVAILABLE_MESSAGE
  }
  return unexpectedErrorMessage(error)
}

/** The message for a failed save. */
export function saveErrorOf(error: unknown): string {
  return error instanceof NotFoundError ? SUMMARY_GONE_MESSAGE : unexpectedErrorMessage(error)
}
