function pad(value: number, length = 2): string {
  return String(value).padStart(length, '0')
}

/**
 * Today's date in the user's own time zone as `YYYY-MM-DD`, worked out at the moment it
 * is called (#2: not UTC). At 08:00 on 2 November in Sydney it is 2026-11-02, while it is
 * still 1 November in UTC.
 */
export function localToday(now: Date = new Date()): string {
  return `${pad(now.getFullYear(), 4)}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** True for a complete `YYYY-MM-DD` date. The native date input is empty while incomplete. */
export function isCompleteDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

/**
 * The calendar date `days` days before `date`, both `YYYY-MM-DD`. Worked out on the
 * calendar date alone (in UTC, where no day is 23 or 25 hours long), so a daylight-saving
 * change in between cannot shift it.
 */
export function daysBefore(date: string, days: number): string {
  const [year, month, day] = date.split('-').map(Number)
  const result = new Date(0)
  result.setUTCFullYear(year, month - 1, day - days)
  return `${pad(result.getUTCFullYear(), 4)}-${pad(result.getUTCMonth() + 1)}-${pad(result.getUTCDate())}`
}

/**
 * True when one of the dates is today or one of the 6 days before it (FR-N1, §7.5): with
 * today 2026-11-12, 2026-11-06 to 2026-11-12. Dates after today do not count. The dates
 * are the stored `YYYY-MM-DD` texts, compared as text, never shifted by time zone; `today`
 * comes from `localToday()`.
 */
export function hasDateInLastSevenDays(dates: Iterable<string>, today: string): boolean {
  const first = daysBefore(today, 6)
  for (const date of dates) {
    if (date >= first && date <= today) {
      return true
    }
  }
  return false
}
