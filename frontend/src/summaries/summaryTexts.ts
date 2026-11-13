// Texts and display helpers of the summaries list and the summary page (#33 and its design
// note). The texts shared with the review page's summary panel are in
// components/summaryEditor.ts; the network and unexpected-error texts are the shared ones
// in auth/requestErrors.ts.
import { formatFullDate, formatShortDate } from '../components/formatDate.ts'
import { localToday } from '../entries/localDate.ts'

export const SUMMARIES_TITLE = 'Summaries'
export const SUMMARY_PAGE_TITLE = 'Summary'

export const LOADING_SUMMARIES_TEXT = 'Loading summaries…'
export const LOADING_SUMMARY_TEXT = 'Loading summary…'

export const NO_SUMMARIES_TEXT = 'No summaries yet. Draft one on the Review page.'
export const GO_TO_REVIEW_LABEL = 'Go to Review'

/** On the list after a delete on the summary page. */
export const SUMMARY_DELETED_MESSAGE = 'Summary deleted.'
/** Deleting answered `not_found`: the summary was deleted meanwhile, for example in another tab. */
export const SUMMARY_GONE_ON_DELETE_MESSAGE = 'This summary was already deleted.'

export const BACK_TO_SUMMARIES = 'Back to summaries'
/** The summary does not exist, belongs to another user, or the id is invalid. */
export const SUMMARY_MISSING_MESSAGE = "This summary doesn't exist."

/** The hint under "Summary text" (§7.4). */
export const EDIT_NOTE = 'Editing changes only this summary. Your entries stay as they are.'

export const COPY_LABEL = 'Copy'
export const COPIED_LABEL = 'Copied'
export const DELETE_LABEL = 'Delete'
export const COPY_FAILED_MESSAGE = "Couldn't copy. Select the text and copy it manually."
/** How long "Copy" says "Copied". */
export const COPIED_MS = 2_000

export const DELETE_SUMMARY_TITLE = 'Delete this summary?'
export const DELETE_SUMMARY_TEXT = "This can't be undone. Your entries are not affected."
export const DELETE_SUMMARY_LABEL = 'Delete summary'

/** The longest preview, before the two-line clamp, so a row's accessible name stays short. */
export const PREVIEW_MAX_LENGTH = 240

/**
 * The user's own day of a stored timestamp, as `YYYY-MM-DD`: `2026-11-12T22:30:00Z` is
 * 2026-11-13 in Sydney. Unlike a summary's period, a creation time is a moment, so it is
 * shown in the user's time zone. A text that is no timestamp is returned as it is.
 */
export function localDateOf(timestamp: string): string {
  const moment = new Date(timestamp)
  return Number.isNaN(moment.getTime()) ? timestamp : localToday(moment)
}

/** The creation date of a summary, in the user's time zone: "13 Nov 2026". */
export function createdDateText(createdAt: string): string {
  return formatFullDate(localDateOf(createdAt))
}

/** The list row's date in two lines, "13 Nov" and "2026". Together they read "13 Nov 2026". */
export function createdDateParts(createdAt: string): { dayMonth: string; year: string } {
  const date = localDateOf(createdAt)
  const full = formatFullDate(date)
  const short = formatShortDate(date)
  // A text that is no date comes back unchanged: show it on one line.
  if (!full.startsWith(`${short} `)) {
    return { dayMonth: full, year: '' }
  }
  return { dayMonth: short, year: full.slice(short.length + 1) }
}

/** "Created 13 Nov 2026". */
export function createdLine(createdAt: string): string {
  return `Created ${createdDateText(createdAt)}`
}

/**
 * The start of a summary's text for its list row: line breaks and every other run of
 * whitespace become one space, and a long text is cut to 240 characters plus "…". The
 * row's CSS then cuts it to two lines.
 */
export function previewText(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > PREVIEW_MAX_LENGTH ? `${flat.slice(0, PREVIEW_MAX_LENGTH).trimEnd()}…` : flat
}
