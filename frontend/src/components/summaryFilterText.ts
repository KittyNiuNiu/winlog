// The description of a summary's filter (#32), shared by the review page's summary panel
// and the summaries pages (#33): "1 Jan 2026 – 30 Jun 2026 · Achievement, Learning · All tags".
import type { SummaryFilter } from '../api/index.ts'
import { CATEGORIES } from './categories.ts'
import { formatFullDate } from './formatDate.ts'

export const ALL_CATEGORIES_TEXT = 'All categories'
export const ALL_TAGS_TEXT = 'All tags'

/**
 * The period (dates exactly as stored, never shifted by a time zone), then the categories
 * in the fixed order or "All categories", then the tags as stored or "All tags".
 */
export function summaryFilterText(filter: SummaryFilter): string {
  const period = `${formatFullDate(filter.period_start)} – ${formatFullDate(filter.period_end)}`
  const chosen = filter.categories ?? []
  const categories = CATEGORIES.filter((category) => chosen.includes(category))
  const tags = filter.tags ?? []
  return [
    period,
    categories.length > 0 ? categories.join(', ') : ALL_CATEGORIES_TEXT,
    tags.length > 0 ? tags.join(', ') : ALL_TAGS_TEXT,
  ].join(' · ')
}
