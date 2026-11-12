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
}

/**
 * An information or error message with its icon. The element is a live region that
 * stays in the page (information: role="status", error: role="alert"), so screen readers
 * announce each new text. The text sits directly in it.
 */
export default function Message({ variant, children, className }: MessageProps) {
  const hasText = children !== null && children !== undefined && children !== false && children !== ''
  return (
    <div
      className={['message', `message--${variant}`, className].filter(Boolean).join(' ')}
      role={variant === 'error' ? 'alert' : 'status'}
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
