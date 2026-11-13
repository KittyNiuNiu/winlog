// Editing a saved summary: the texts and helpers shared by the review page's summary panel
// (#32) and the summary page (#33), so both say the same thing. The server's own message
// is never shown.
import { NotFoundError } from '../api/index.ts'
import { unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { SUMMARY_TEXT_MAX_CHARACTERS, formatCount, overLimit } from './inputLimits.ts'

export const SUMMARY_FIELD_LABEL = 'Summary text'
export const SAVE_SUMMARY_LABEL = 'Save summary'
export const SAVING_LABEL = 'Saving…'

export const SUMMARY_SAVED_TEXT = 'Summary saved.'
export const EMPTY_SUMMARY_TEXT = 'Write your summary, then save.'
export const SUMMARY_TOO_LONG_TEXT = `Shorten the summary to ${formatCount(SUMMARY_TEXT_MAX_CHARACTERS)} characters, then save.`
export const SUMMARY_GONE_MESSAGE = "This summary no longer exists, so your changes can't be saved."

/** Which entries a summary is from: "Entries from " + `summaryFilterText(filter)`. */
export function sourceLine(filterText: string): string {
  return `Entries from ${filterText}`
}

/** The message for a failed save. */
export function saveErrorOf(error: unknown): string {
  return error instanceof NotFoundError ? SUMMARY_GONE_MESSAGE : unexpectedErrorMessage(error)
}

/**
 * The "Summary text" field's message after Save checked it, or null. Empty text and text
 * over the limit (#43) never happen together.
 */
export function summaryTextProblem(text: string): string | null {
  if (text.trim() === '') {
    return EMPTY_SUMMARY_TEXT
  }
  if (overLimit(text, SUMMARY_TEXT_MAX_CHARACTERS)) {
    return SUMMARY_TOO_LONG_TEXT
  }
  return null
}
