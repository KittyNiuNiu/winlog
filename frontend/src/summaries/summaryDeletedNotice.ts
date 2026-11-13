// After a delete on the summary page, the user goes to `/summaries`, which shows "Summary
// deleted." or "This summary was already deleted." once (#33), as `entrySavedNotice.ts`
// does for "Entry saved.". The navigation carries this state; the list shows the message
// and then replaces its history entry without it, so a reload or a later visit does not
// show it again.

const SUMMARY_DELETED_KEY = 'summaryDeleted'

/** "deleted": the delete worked. "gone": the summary was already deleted (`not_found`). */
export type SummaryDeletedNotice = 'deleted' | 'gone'

/** The navigation state for `/summaries` after a delete. */
export function summaryDeletedState(notice: SummaryDeletedNotice): Record<string, unknown> {
  return { [SUMMARY_DELETED_KEY]: notice }
}

/** The notice the navigation state carries, or null. */
export function summaryDeletedNoticeOf(state: unknown): SummaryDeletedNotice | null {
  if (typeof state !== 'object' || state === null) {
    return null
  }
  const notice = (state as Record<string, unknown>)[SUMMARY_DELETED_KEY]
  return notice === 'deleted' || notice === 'gone' ? notice : null
}
