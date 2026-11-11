import type { Entry } from '../api/index.ts'
import CategoryLabel from './CategoryLabel.tsx'
import { formatShortDate } from './formatDate.ts'
import './EntryRow.css'

interface EntryRowProps {
  entry: Pick<Entry, 'date' | 'category' | 'text' | 'result_impact'>
}

/**
 * One entry in a list: date, category label and text, with "Result: …" below when the
 * entry has a result. A hairline above, no card. Phone: the label sits above the text.
 * Laptop: three columns.
 */
export default function EntryRow({ entry }: EntryRowProps) {
  const result = entry.result_impact
  return (
    <div className="entry-row">
      <time className="entry-row__date" dateTime={entry.date}>
        {formatShortDate(entry.date)}
      </time>
      <div className="entry-row__category">
        <CategoryLabel category={entry.category} />
      </div>
      <div className="entry-row__body">
        <p className="entry-row__text">{entry.text}</p>
        {result !== null && result !== '' && (
          <p className="entry-row__result">
            <span className="entry-row__result-label">Result:</span> {result}
          </p>
        )}
      </div>
    </div>
  )
}
