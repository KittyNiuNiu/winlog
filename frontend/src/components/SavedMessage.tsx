import { CircleCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import Icon from './Icon.tsx'
import type { SavedMessagePhase } from './useSavedMessage.ts'
import './SavedMessage.css'

interface SavedMessageProps {
  /** From `useSavedMessage()`. */
  phase: SavedMessagePhase
  /** From `useSavedMessage()`. */
  count: number
  /** The text, for example "Entry saved." */
  children: ReactNode
}

/**
 * A saved-peach band with a plum check, for example "Entry saved." It sits in a status
 * region that stays in the page, so screen readers announce it without moving focus.
 * The band itself stays while it is shown again, so it does not enter a second time; only
 * its text is replaced, so screen readers announce it again.
 */
export default function SavedMessage({ phase, count, children }: SavedMessageProps) {
  return (
    <div className={`saved-region${phase === 'leaving' ? ' saved-region--leaving' : ''}`} role="status">
      {phase !== 'hidden' && (
        <div className="saved-message">
          <Icon className="saved-message__icon" icon={CircleCheck} size={20} />
          <span key={count}>{children}</span>
        </div>
      )}
    </div>
  )
}
