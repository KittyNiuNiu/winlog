// The maximum input sizes of the forms (#43, product-spec.md §6 and §7.4). They are the
// field limits of `openapi.yaml` (EntryInput, SummaryUpdate), fixed in the contract; the
// backend stays the authority. The summary input limit (AI_SUMMARY_MAX_INPUT_CHARACTERS) is
// a server setting and is not checked here.

export const ENTRY_TEXT_MAX_CHARACTERS = 2000
export const RESULT_MAX_CHARACTERS = 500
export const TAG_NAME_MAX_CHARACTERS = 40
export const TAGS_PER_ENTRY_MAX = 10
export const SUMMARY_TEXT_MAX_CHARACTERS = 10000

/** The counter under a field shows from this share of its limit (the #43 design note). */
const COUNTER_FROM = 0.8

/**
 * The number of characters in `value` as the backend counts them: Unicode code points, not
 * UTF-16 units, so an emoji counts as one. Line breaks count as one character each.
 */
export function characterCount(value: string): number {
  // A string iterates by code point, as in passwordProblems (auth/validation.ts).
  return Array.from(value).length
}

/** Whether `value` has more characters than `limit`. */
export function overLimit(value: string, limit: number): boolean {
  return characterCount(value) > limit
}

const NUMBER = new Intl.NumberFormat('en-US')

/** A count in English format whatever the browser's locale, for example "1,600". */
export function formatCount(count: number): string {
  return NUMBER.format(count)
}

/** The counter of a field, or null below 80% of its limit, when no counter shows. */
export interface CharacterCounter {
  /** What the counter shows, for example "1,600 / 2,000". */
  visible: string
  /** What screen readers read instead, for example "1,600 of 2,000 characters". */
  spoken: string
  over: boolean
}

export function characterCounter(value: string, limit: number): CharacterCounter | null {
  const count = characterCount(value)
  if (count < limit * COUNTER_FROM) {
    return null
  }
  return {
    visible: `${formatCount(count)} / ${formatCount(limit)}`,
    spoken: `${formatCount(count)} of ${formatCount(limit)} characters`,
    over: count > limit,
  }
}
