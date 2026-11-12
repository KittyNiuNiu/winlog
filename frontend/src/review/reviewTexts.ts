// Texts of the review page (#31 and its design note).

export const DATE_ORDER_ERROR = 'Choose a start date on or before the end date.'
export const NO_MATCH_TEXT = 'No entries match these filters.'
export const NO_ENTRIES_TEXT = 'No entries yet. Write your first win.'

/** "1 entry", "12 entries", "0 entries". */
export function entryCountText(count: number): string {
  return `${count} ${count === 1 ? 'entry' : 'entries'}`
}
