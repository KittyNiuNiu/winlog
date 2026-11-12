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
