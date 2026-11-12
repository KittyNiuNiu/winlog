// The entry form's own texts (#27 and its design note), and the entries page's (#29). The
// network and unexpected-error texts are the shared ones in auth/requestErrors.ts.

export const ENTRY_SAVED_MESSAGE = 'Entry saved.'

/** Field messages: the same text for the app's own check and for a server error. */
export const TEXT_PROBLEM = 'Write what happened, then save.'
export const DATE_PROBLEM = 'Choose a date, then save.'
export const CATEGORY_PROBLEM = 'Choose a category, then save.'
export const TAGS_PROBLEM = 'Check your tags, then save.'
export const RESULT_PROBLEM = 'Check the result, then save.'

/** Saving an edit answered `not_found`: the entry was deleted meanwhile. */
export const ENTRY_GONE_MESSAGE = "This entry no longer exists, so it can't be saved."
/** The edit page's entry does not exist, belongs to another user, or the id is invalid. */
export const ENTRY_MISSING_MESSAGE = "This entry doesn't exist."

/** The entries page (#29): after a delete. */
export const ENTRY_DELETED_MESSAGE = 'Entry deleted.'
/** Deleting answered `not_found`: the entry was deleted meanwhile, for example in another tab. */
export const ENTRY_GONE_ON_DELETE_MESSAGE = 'This entry was already deleted.'
