// Tag names in the entry form. Names are trimmed and compared without regard to case
// (FR-E3); a name keeps the spelling it was first added with.

function sameName(a: string, b: string): boolean {
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
