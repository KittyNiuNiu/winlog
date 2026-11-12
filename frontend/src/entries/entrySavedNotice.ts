// After saving an edit, the user goes to `/`, which shows "Entry saved." once (#27). The
// navigation carries this state; `/` shows the message and then replaces its history entry
// without it, so a reload or a later visit does not show it again.

const ENTRY_SAVED_KEY = 'entrySaved'

/** The navigation state for `/` after saving an edit. */
export function entrySavedState(): Record<string, unknown> {
  return { [ENTRY_SAVED_KEY]: true }
}

/** True when the navigation state comes from saving an edit. */
export function cameFromEntrySave(state: unknown): boolean {
  return typeof state === 'object' && state !== null && (state as Record<string, unknown>)[ENTRY_SAVED_KEY] === true
}
