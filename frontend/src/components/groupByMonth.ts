import { formatMonthHeading } from './formatDate.ts'

export interface MonthGroup<T> {
  /** "YYYY-MM" */
  key: string
  /** For example "November 2026". */
  heading: string
  entries: T[]
}

/**
 * Entries split into months, in the order they come. The API sorts by date, newest
 * first, so each month is one run of entries and the page does not sort again. Used by
 * the entries page (#29) and inside each category on the review page (#31).
 */
export function groupByMonth<T extends { date: string }>(entries: readonly T[]): MonthGroup<T>[] {
  const groups: MonthGroup<T>[] = []
  for (const entry of entries) {
    const key = entry.date.slice(0, 7)
    const last = groups.at(-1)
    if (last !== undefined && last.key === key) {
      last.entries.push(entry)
    } else {
      groups.push({ key, heading: formatMonthHeading(entry.date), entries: [entry] })
    }
  }
  return groups
}
