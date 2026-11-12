// The review page's filter (FR-R1, #31). It lives in the page URL with the same names as
// `GET /entries`, so the URL, the controls and the request always show the same filter,
// and the summary (#32) can use exactly the filter that is shown.
import type { Category, EntryListQuery } from '../api/index.ts'
import { CATEGORIES } from '../components/categories.ts'
import { addTagNames } from '../entries/tagNames.ts'

export interface ReviewFilter {
  /** `YYYY-MM-DD`, or null when not set. */
  startDate: string | null
  /** `YYYY-MM-DD`, or null when not set. */
  endDate: string | null
  /** The selected categories, in the fixed order. None means all categories. */
  categories: Category[]
  /** The selected tags: trimmed, never empty, each once (ignoring case). None means all tags. */
  tags: string[]
}

export const NO_FILTER: ReviewFilter = { startDate: null, endDate: null, categories: [], tags: [] }

/**
 * Whether `value` is a real calendar date written as `YYYY-MM-DD` ("2026-02-30" and "abc"
 * are not). Checked on the text, so no time zone plays a part.
 */
export function isDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (match === null) {
    return false
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  // There is no year 0 (the API rejects it).
  if (year < 1 || month < 1 || month > 12 || day < 1) {
    return false
  }
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0
  const daysInMonth = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
  return day <= daysInMonth
}

/** A date from the URL or a date input, or null when it is empty, incomplete or not real. */
export function dateOrNull(value: string | null): string | null {
  return value !== null && isDate(value) ? value : null
}

function isCategory(value: string): value is Category {
  return (CATEGORIES as readonly string[]).includes(value)
}

/** The filter in the URL's query. Values the page cannot use are left out. */
export function parseFilter(params: URLSearchParams): ReviewFilter {
  const categories = params.getAll('category').filter(isCategory)
  return {
    startDate: dateOrNull(params.get('start_date')),
    endDate: dateOrNull(params.get('end_date')),
    categories: CATEGORIES.filter((category) => categories.includes(category)),
    tags: addTagNames([], params.getAll('tag')),
  }
}

/** The URL query for a filter: only the filters in use, so no filter gives an empty query. */
export function filterSearchParams(filter: ReviewFilter): URLSearchParams {
  const params = new URLSearchParams()
  if (filter.startDate !== null) {
    params.set('start_date', filter.startDate)
  }
  if (filter.endDate !== null) {
    params.set('end_date', filter.endDate)
  }
  for (const category of filter.categories) {
    params.append('category', category)
  }
  for (const tag of filter.tags) {
    params.append('tag', tag)
  }
  return params
}

/** The `GET /entries` query for a filter: a filter not in use is left out entirely. */
export function entryQuery(filter: ReviewFilter): EntryListQuery {
  const query: EntryListQuery = {}
  if (filter.startDate !== null) {
    query.start_date = filter.startDate
  }
  if (filter.endDate !== null) {
    query.end_date = filter.endDate
  }
  if (filter.categories.length > 0) {
    query.category = [...filter.categories]
  }
  const tags = filter.tags.map((tag) => tag.trim()).filter((tag) => tag !== '')
  if (tags.length > 0) {
    query.tag = tags
  }
  return query
}

/** The number of filters in use: each set date, each selected category and each selected tag. */
export function filtersInUse(filter: ReviewFilter): number {
  return (
    (filter.startDate === null ? 0 : 1) +
    (filter.endDate === null ? 0 : 1) +
    filter.categories.length +
    filter.tags.length
  )
}

/** Whether the start date is after the end date. Then no request is sent. */
export function startAfterEnd(filter: ReviewFilter): boolean {
  // `YYYY-MM-DD` texts compare in date order.
  return filter.startDate !== null && filter.endDate !== null && filter.startDate > filter.endDate
}

/** `categories` with `category` added or removed, in the fixed order. */
export function toggleCategory(categories: readonly Category[], category: Category): Category[] {
  const selected = categories.includes(category)
  return CATEGORIES.filter((each) => (each === category ? !selected : categories.includes(each)))
}
