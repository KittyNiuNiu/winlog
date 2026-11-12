import type { ReactNode } from 'react'
import './EmptyState.css'

interface EmptyStateProps {
  /** The sentence that says what is empty and what to do. */
  children: ReactNode
  /** One action: a button or a link. */
  action: ReactNode
  /** An optional decorative illustration, up to 200×160px (#77). */
  illustration?: ReactNode
}

/** An empty state: an optional illustration, a sentence and one action, centred. */
export default function EmptyState({ children, action, illustration }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {illustration !== undefined && (
        <div className="empty-state__illustration" aria-hidden="true">
          {illustration}
        </div>
      )}
      <p className="empty-state__text">{children}</p>
      <div className="empty-state__action">{action}</div>
    </div>
  )
}
