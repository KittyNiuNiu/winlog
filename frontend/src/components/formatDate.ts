const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * The day and short month of a stored `YYYY-MM-DD` date, for example "10 Nov". It is
 * built from the parts of the text, so no time zone can shift the day (`new Date()` reads
 * the text as UTC midnight), and September is "Sep" (Intl's en-GB writes "Sept").
 */
export function formatShortDate(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  const month = match === null ? undefined : MONTHS[Number(match[2]) - 1]
  if (match === null || month === undefined) {
    return date
  }
  return `${Number(match[3])} ${month}`
}
