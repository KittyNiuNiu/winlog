// AI suggestions on the entry form (FR-S1 to FR-S3, #28): which values the AI put in the
// form, how an answer is applied, how suggestions are discarded, and the notice for a
// failed request. Suggestions fill only what is still empty and never override the user.
import { AiUnavailableError, LimitReachedError, type Category, type Suggestion } from '../api/index.ts'
import { unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { GLOBAL_LIMIT_MESSAGE } from '../components/aiTexts.ts'
import { addTagNamesWithin, sameName } from './tagNames.ts'

export const SUGGEST_LABEL = 'Suggest category and tags'
export const SUGGESTING_LABEL = 'Suggesting…'
export const DISCARD_SUGGESTIONS_LABEL = 'Discard suggestions'
export const SUGGESTED_MARK = 'Suggested'

/** The "Suggested: <category>" hint. */
export function suggestedCategoryHint(category: Category): string {
  return `Suggested: ${category}`
}

export const SUGGESTIONS_UNAVAILABLE_MESSAGE =
  "Suggestions aren't available right now. You can fill in the fields yourself."
export const USER_SUGGESTION_LIMIT_MESSAGE =
  "You've used today's suggestions. They're available again after midnight UTC."
// Shared with the summary panel; exported here too, as before (#28).
export { GLOBAL_LIMIT_MESSAGE }

/** The notice for a failed suggestion request. It never shows the server's message. */
export function suggestionNoticeOf(error: unknown): string {
  if (error instanceof LimitReachedError) {
    if (error.limit === 'user_suggestions') {
      return USER_SUGGESTION_LIMIT_MESSAGE
    }
    if (error.limit === 'global') {
      return GLOBAL_LIMIT_MESSAGE
    }
    // No limit named, or one that is not about suggestions.
    return SUGGESTIONS_UNAVAILABLE_MESSAGE
  }
  if (error instanceof AiUnavailableError) {
    return SUGGESTIONS_UNAVAILABLE_MESSAGE
  }
  return unexpectedErrorMessage(error)
}

/** What the AI put in the form and the user has not made their own yet. */
export interface Marks {
  /** The category a suggestion filled in, while it is still marked "Suggested". */
  category: Category | null
  /** A suggested category that differs from the user's, shown as "Suggested: <category>". */
  hint: Category | null
  /** The suggested tags on the entry, marked "Suggested", in their stored spelling. */
  tags: string[]
}

export const NO_MARKS: Marks = { category: null, hint: null, tags: [] }

/** The parts of the form a suggestion fills. */
interface Suggestible {
  category: Category | null
  tags: string[]
}

interface Suggested<V extends Suggestible> {
  values: V
  marks: Marks
}

export function hasSuggestions(marks: Marks): boolean {
  return marks.category !== null || marks.hint !== null || marks.tags.length > 0
}

/**
 * "Discard suggestions": removes the suggested tags, clears a category still marked
 * "Suggested" and drops the hint. The user's own tags and category stay.
 */
export function discardSuggestions<V extends Suggestible>({ values, marks }: Suggested<V>): Suggested<V> {
  return {
    values: {
      ...values,
      category: marks.category !== null && values.category === marks.category ? null : values.category,
      tags: values.tags.filter((tag) => !marks.tags.includes(tag)),
    },
    marks: NO_MARKS,
  }
}

/**
 * Applies an answer to the form as it is now: the earlier suggestions are discarded first,
 * then an empty category is filled and marked, a different chosen category gets the hint,
 * and new tags are added at the end and marked. `addedTags` says whether a tag was added.
 */
export function applySuggestion<V extends Suggestible>(
  form: Suggested<V>,
  suggestion: Suggestion,
): Suggested<V> & { addedTags: boolean } {
  const { values } = discardSuggestions(form)
  const marks: Marks = { category: null, hint: null, tags: [] }
  let category = values.category
  if (category === null) {
    category = suggestion.category
    marks.category = suggestion.category
  } else if (category !== suggestion.category) {
    marks.hint = suggestion.category
  }
  // Only until the entry has 10 tags (#43); the rest are not added.
  const { tags } = addTagNamesWithin(values.tags, suggestion.tags)
  marks.tags = tags.slice(values.tags.length)
  return { values: { ...values, category, tags }, marks, addedTags: marks.tags.length > 0 }
}

/**
 * The marks after the user changed the tags: removed tags lose their mark, and a tag whose
 * name the user typed or chose (ignoring case) becomes the user's own.
 */
export function marksAfterTagChange(marks: Marks, tags: readonly string[], typed: readonly string[]): Marks {
  const kept = marks.tags.filter(
    (tag) => tags.includes(tag) && !typed.some((name) => sameName(name.trim(), tag)),
  )
  return kept.length === marks.tags.length ? marks : { ...marks, tags: kept }
}

/**
 * The marks after the user chose a category (a chip or the hint): the category is the
 * user's own, so its mark goes; the hint goes once the chosen category is the suggested one.
 */
export function marksAfterCategoryChoice(marks: Marks, category: Category): Marks {
  return { ...marks, category: null, hint: marks.hint === category ? null : marks.hint }
}
