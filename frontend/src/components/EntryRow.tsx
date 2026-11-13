import { Pencil, Trash2 } from 'lucide-react'
import type { Ref } from 'react'
import { Link } from 'react-router'
import type { Entry } from '../api/index.ts'
import CategoryLabel from './CategoryLabel.tsx'
import { formatFullDate, formatShortDate } from './formatDate.ts'
import Icon from './Icon.tsx'
import './EntryRow.css'

/** The row's Edit and Delete actions (#29). */
export interface EntryRowActions {
  /** Where Edit leads, for example `/entries/:id/edit`. */
  editTo: string
  onDelete: () => void
}

interface EntryRowProps {
  entry: Pick<Entry, 'date' | 'category' | 'text' | 'result_impact'>
  /** Read-only tags below the text. Not given or empty: no tag area. */
  tags?: string[]
  /** Edit and Delete. Not given: the row has no actions. */
  actions?: EntryRowActions
  /** The Edit link, for moving focus to it. */
  editRef?: Ref<HTMLAnchorElement>
  /** The Delete button, for moving focus to it. */
  deleteRef?: Ref<HTMLButtonElement>
}

/**
 * One entry in a list: date, category label and text, with "Result: …" below when the
 * entry has a result, and optionally the tags and the Edit and Delete actions. A hairline
 * above, no card. Phone: the label (and the actions to its right) sits above the text.
 * Laptop: three columns, with the actions under the label.
 */
export default function EntryRow({ entry, tags, actions, editRef, deleteRef }: EntryRowProps) {
  const result = entry.result_impact
  const fullDate = formatFullDate(entry.date)
  return (
    <div className="entry-row">
      <time className="entry-row__date" dateTime={entry.date}>
        {formatShortDate(entry.date)}
      </time>
      <div className={`entry-row__category${actions === undefined ? '' : ' entry-row__category--with-actions'}`}>
        <CategoryLabel category={entry.category} />
        {actions !== undefined && (
          <div className="entry-row__actions">
            <Link
              ref={editRef}
              className="entry-row__action"
              to={actions.editTo}
              aria-label={`Edit entry from ${fullDate}`}
            >
              <Icon icon={Pencil} size={20} />
            </Link>
            <button
              ref={deleteRef}
              className="entry-row__action"
              type="button"
              aria-label={`Delete entry from ${fullDate}`}
              onClick={actions.onDelete}
            >
              <Icon icon={Trash2} size={20} />
            </button>
          </div>
        )}
      </div>
      <div className="entry-row__body">
        <p className="entry-row__text">{entry.text}</p>
        {result !== null && result !== '' && (
          <p className="entry-row__result">
            <span className="entry-row__result-label">Result:</span> {result}
          </p>
        )}
        {tags !== undefined && tags.length > 0 && (
          <ul className="entry-row__tags" aria-label="Tags">
            {tags.map((tag) => (
              <li className="entry-row__tag" key={tag}>
                {tag}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
