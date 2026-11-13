import type { MouseEvent } from 'react'
import { Link } from 'react-router'
import { REGISTER_PATH } from '../auth/wantedPage.ts'
import { CREATE_OWN_ACCOUNT_LABEL, DEMO_NOTICE_TEXT, LEAVING_DEMO_LABEL } from './demoTexts.ts'
import Message from './Message.tsx'
import './DemoNotice.css'

interface DemoNoticeProps {
  /** True while "Create your own account" logs out: spinner and "Leaving the demo…". */
  busy: boolean
  /** True while any logout runs, so a press does nothing. */
  inactive: boolean
  /** Logs out of the demo and opens /register. */
  onCreateAccount: () => void
}

/**
 * The notice on every app page of a demo session (FR-X1, §7.7). It looks like an
 * information message but is not a live region, so it is not announced again on each page
 * change, and it cannot be closed.
 */
export default function DemoNotice({ busy, inactive, onCreateAccount }: DemoNoticeProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    // The link only opens /register after the logout, never on its own.
    event.preventDefault()
    if (!inactive) {
      onCreateAccount()
    }
  }

  return (
    <Message variant="info" live={false} className="demo-notice">
      <p className="demo-notice__text">{DEMO_NOTICE_TEXT}</p>
      <Link
        className={`demo-notice__link${busy ? ' demo-notice__link--busy' : ''}`}
        to={REGISTER_PATH}
        aria-disabled={inactive ? 'true' : undefined}
        onClick={handleClick}
      >
        {busy && <span className="spinner" aria-hidden="true" />}
        {busy ? LEAVING_DEMO_LABEL : CREATE_OWN_ACCOUNT_LABEL}
      </Link>
    </Message>
  )
}
