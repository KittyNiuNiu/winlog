// The texts of the settings page (FR-D1, FR-D2; design note on #34).

export const SETTINGS_PAGE_TITLE = 'Settings'

export const YOUR_DATA_HEADING = 'Your data'
export const YOUR_DATA_TEXT =
  'Download all your entries and summaries. JSON is complete and machine-readable. Markdown is easy to read.'
export const DOWNLOAD_JSON_LABEL = 'Download JSON'
export const DOWNLOAD_MARKDOWN_LABEL = 'Download Markdown'
export const DOWNLOADING_LABEL = 'Downloading…'

export const ACCOUNT_HEADING = 'Account'
export const ACCOUNT_TEXT = 'Deleting your account removes all of your data.'
export const DELETE_ACCOUNT_LABEL = 'Delete account'

export const DELETE_STEP_TITLE = 'Delete your account?'
export const DELETE_STEP_TEXT =
  "This permanently deletes your account and all your entries, tags and summaries. This can't be undone."
export const DELETE_STEP_DOWNLOAD_TEXT = 'Download your data first if you want to keep it.'
export const CURRENT_PASSWORD_LABEL = 'Current password'
export const CONFIRM_WORD = 'delete'
export const CONFIRM_LABEL = `Type "${CONFIRM_WORD}" to confirm`
export const CANCEL_LABEL = 'Cancel'
export const DELETE_MY_ACCOUNT_LABEL = 'Delete my account'
export const DELETING_LABEL = 'Deleting…'
export const WRONG_PASSWORD_MESSAGE = 'That password is incorrect.'

/** True when the confirmation field holds the word, in any case, with spaces around it or not. */
export function isConfirmWord(value: string): boolean {
  return value.trim().toLowerCase() === CONFIRM_WORD
}
