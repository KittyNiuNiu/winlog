import { CircleExclamationPoint, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import Icon from './Icon.tsx'
import './Message.css'

interface MessageProps {
  /** Information (for example the waking-up hint) or error (for example a failed login). */
  variant: 'info' | 'error'
  /** The text. Null or empty hides the message but keeps its live region in the page. */
  children?: ReactNode
  className?: string
  /**
   * False for a message that stays on every page, such as the demo notice (#35): no
   * `role`, so screen readers do not announce it again on each page change.
   */
  live?: boolean
}

/**
 * An information or error message with its icon. By default the element is a live region
 * that stays in the page (information: role="status", error: role="alert"), so screen
 * readers announce each new text. The text sits directly in it.
 */
export default function Message({ variant, children, className, live = true }: MessageProps) {
  const hasText = children !== null && children !== undefined && children !== false && children !== ''
  return (
    <div
      className={['message', `message--${variant}`, className].filter(Boolean).join(' ')}
      role={live ? (variant === 'error' ? 'alert' : 'status') : undefined}
    >
      {hasText && (
        <>
          <Icon className="message__icon" icon={variant === 'error' ? CircleExclamationPoint : Info} size={20} />
          {children}
        </>
      )}
    </div>
  )
}
