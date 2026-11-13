const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const FULL_MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

interface DateParts {
  year: string
  /** 0 for January. */
  month: number
  day: number
}

/**
 * The parts of a stored `YYYY-MM-DD` date, or null when the text is not one. They are read
 * from the text, so no time zone can shift the day (`new Date()` reads the text as UTC
 * midnight) and the browser's language does not change the month names.
 */
function dateParts(date: string): DateParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (match === null) {
    return null
  }
  const month = Number(match[2]) - 1
  if (MONTHS[month] === undefined) {
    return null
  }
  return { year: match[1], month, day: Number(match[3]) }
}

/** The day and short month of a stored date, for example "10 Nov" (September is "Sep"). */
export function formatShortDate(date: string): string {
  const parts = dateParts(date)
  return parts === null ? date : `${parts.day} ${MONTHS[parts.month]}`
}

/** The day, short month and year of a stored date, for example "10 Nov 2026". */
export function formatFullDate(date: string): string {
  const parts = dateParts(date)
  return parts === null ? date : `${parts.day} ${MONTHS[parts.month]} ${parts.year}`
}

/** The full English month and the year of a stored date, for example "November 2026". */
export function formatMonthHeading(date: string): string {
  const parts = dateParts(date)
  return parts === null ? date : `${FULL_MONTHS[parts.month]} ${parts.year}`
}
