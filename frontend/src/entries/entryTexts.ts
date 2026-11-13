// The entry form's own texts (#27 and its design note), and the entries page's (#29). The
// network and unexpected-error texts are the shared ones in auth/requestErrors.ts.
import {
  ENTRY_TEXT_MAX_CHARACTERS,
  RESULT_MAX_CHARACTERS,
  TAGS_PER_ENTRY_MAX,
  TAG_NAME_MAX_CHARACTERS,
  formatCount,
} from '../components/inputLimits.ts'

export const ENTRY_SAVED_MESSAGE = 'Entry saved.'

/** Field messages: the same text for the app's own check and for a server error. */
export const TEXT_PROBLEM = 'Write what happened, then save.'
export const DATE_PROBLEM = 'Choose a date, then save.'
export const CATEGORY_PROBLEM = 'Choose a category, then save.'
export const TAGS_PROBLEM = 'Check your tags, then save.'
export const RESULT_PROBLEM = 'Check the result, then save.'

/** The maximum input sizes (#43 and its design note). */
export const TEXT_TOO_LONG = `Shorten the text to ${formatCount(ENTRY_TEXT_MAX_CHARACTERS)} characters, then save.`
export const RESULT_TOO_LONG = `Shorten the result to ${formatCount(RESULT_MAX_CHARACTERS)} characters, then save.`
export const TAG_TOO_LONG = `Tags can be up to ${TAG_NAME_MAX_CHARACTERS} characters.`
export const TOO_MANY_TAGS = `Up to ${TAGS_PER_ENTRY_MAX} tags per entry.`
/** Under the suggest button while it is disabled because the text is too long. */
export const SUGGEST_LIMIT_HINT = `Suggestions work on up to ${formatCount(ENTRY_TEXT_MAX_CHARACTERS)} characters.`

/** Saving an edit answered `not_found`: the entry was deleted meanwhile. */
export const ENTRY_GONE_MESSAGE = "This entry no longer exists, so it can't be saved."
/** The edit page's entry does not exist, belongs to another user, or the id is invalid. */
export const ENTRY_MISSING_MESSAGE = "This entry doesn't exist."

/** The entries page (#29): after a delete. */
export const ENTRY_DELETED_MESSAGE = 'Entry deleted.'
/** Deleting answered `not_found`: the entry was deleted meanwhile, for example in another tab. */
export const ENTRY_GONE_ON_DELETE_MESSAGE = 'This entry was already deleted.'
