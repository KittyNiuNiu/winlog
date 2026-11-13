// Tag names in the entry form. Names are trimmed and compared without regard to case
// (FR-E3); a name keeps the spelling it was first added with.
import { TAGS_PER_ENTRY_MAX, TAG_NAME_MAX_CHARACTERS, characterCount } from '../components/inputLimits.ts'

/** Whether two tag names are the same tag (ignoring case). */
export function sameName(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase()
}

/**
 * `current` with each of `names` added at the end: trimmed, without empty names, and
 * without names that are already there when case is ignored.
 */
export function addTagNames(current: readonly string[], names: readonly string[]): string[] {
  const result = [...current]
  for (const raw of names) {
    const name = raw.trim()
    if (name !== '' && !result.some((existing) => sameName(existing, name))) {
      result.push(name)
    }
  }
  return result
}

/** The known tags whose names contain `typed` (ignoring case), leaving out added ones. */
export function matchingTags(known: readonly string[], added: readonly string[], typed: string): string[] {
  const query = typed.trim().toLowerCase()
  if (query === '') {
    return []
  }
  return known.filter(
    (name) => name.toLowerCase().includes(query) && !added.some((existing) => sameName(existing, name)),
  )
}

/** The known tags with `names` added, sorted alphabetically without regard to case. */
export function mergeKnownTags(known: readonly string[], names: readonly string[]): string[] {
  return addTagNames(known, names).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
}

/** Which tag limit an add or a save broke (#43). */
export interface TagLimitProblems {
  /** A name has more than 40 characters (trimmed). */
  tooLong: boolean
  /** A name would be an 11th tag. */
  tooMany: boolean
}

export const NO_TAG_PROBLEMS: TagLimitProblems = { tooLong: false, tooMany: false }

function tooLongName(name: string): boolean {
  return characterCount(name.trim()) > TAG_NAME_MAX_CHARACTERS
}

/**
 * `addTagNames` within the tag limits (#43): names are added in order while they have at
 * most 40 characters (trimmed) and the entry has fewer than 10 tags. The names that did
 * not fit are returned in `rejected` (trimmed, in order), with the limits they broke.
 */
export function addTagNamesWithin(
  current: readonly string[],
  names: readonly string[],
): { tags: string[]; rejected: string[]; problems: TagLimitProblems } {
  const tags = [...current]
  const rejected: string[] = []
  const problems = { ...NO_TAG_PROBLEMS }
  for (const raw of names) {
    const name = raw.trim()
    if (name === '' || tags.some((existing) => sameName(existing, name))) {
      continue
    }
    if (tooLongName(name)) {
      problems.tooLong = true
      rejected.push(name)
    } else if (tags.length >= TAGS_PER_ENTRY_MAX) {
      problems.tooMany = true
      rejected.push(name)
    } else {
      tags.push(name)
    }
  }
  return { tags, rejected, problems }
}

/** The names left in the tag input, so the user sees them all: joined with ", ". */
export function joinTagNames(names: readonly string[]): string {
  return names.join(', ')
}

/**
 * Which tag limits the tags and the tag input still break: a name over 40 characters in the
 * input or among the tags, and more than 10 tags, or 10 with a name still in the input. A
 * tag message shows only while its limit is still broken (the #43 design note).
 */
export function tagLimitProblems(tags: readonly string[], input: string): TagLimitProblems {
  const typed = input.split(',').filter((name) => name.trim() !== '')
  return {
    tooLong: typed.some(tooLongName) || tags.some(tooLongName),
    tooMany: tags.length > TAGS_PER_ENTRY_MAX || (tags.length >= TAGS_PER_ENTRY_MAX && typed.length > 0),
  }
}
