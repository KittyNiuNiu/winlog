import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { listSummaries, type Summary } from '../api/index.ts'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { Button, ButtonLink } from '../components/Button.tsx'
import { focusWhenShown } from '../components/focus.ts'
import EmptyState from '../components/EmptyState.tsx'
import Message from '../components/Message.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import { summaryFilterText } from '../components/summaryFilterText.ts'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import { summaryDeletedNoticeOf } from '../summaries/summaryDeletedNotice.ts'
import {
  GO_TO_REVIEW_LABEL,
  LOADING_SUMMARIES_TEXT,
  NO_SUMMARIES_TEXT,
  SUMMARIES_TITLE,
  SUMMARY_DELETED_MESSAGE,
  SUMMARY_GONE_ON_DELETE_MESSAGE,
  createdDateParts,
  previewText,
} from '../summaries/summaryTexts.ts'
import './SummariesPage.css'

type Load =
  | { status: 'loading' }
  | { status: 'loaded'; summaries: Summary[] }
  | { status: 'failed'; message: string }

/**
 * One summary in the list: the whole row is one link to its page, with the creation date
 * in the 64px date column, then the filter line and the start of the text (#33 design
 * note). A hairline above, no card.
 */
function SummaryRow({ summary }: { summary: Summary }) {
  const { dayMonth, year } = createdDateParts(summary.created_at)
  return (
    <Link className="summary-row" to={`/summaries/${summary.id}`}>
      <time className="summary-row__date" dateTime={summary.created_at}>
        {dayMonth}
        {year !== '' && (
          <>
            {' '}
            <span className="summary-row__year">{year}</span>
          </>
        )}
      </time>
      <span className="summary-row__body">
        <span className="summary-row__filter">{summaryFilterText(summary.filter)}</span>
        <span className="summary-row__preview">{previewText(summary.text)}</span>
      </span>
    </Link>
  )
}

// All of the user's saved summaries, newest first, each opening its own page (FR-R4,
// FR-R5). After a delete on that page, it shows "Summary deleted." or "This summary was
// already deleted." once.
export default function SummariesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const saved = useSavedMessage()
  const { show: showSaved } = saved
  const notice = summaryDeletedNoticeOf(location.state)
  // "This summary was already deleted." stays until the user leaves the page.
  const [goneShown] = useState(notice === 'gone')
  const [attempt, setAttempt] = useState(0)
  const [load, setLoad] = useState<Load & { attempt: number }>({ status: 'loading', attempt: 0 })
  // A new attempt starts loading again.
  const current: Load = load.attempt === attempt ? load : { status: 'loading' }
  const wakingUp = useWakingUpHint(current.status === 'loading')
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (notice === null) {
      return
    }
    if (notice === 'deleted') {
      showSaved()
    }
    // The summary page the user was on is gone: start again at the title.
    headingRef.current?.focus()
    // Forget it, so a reload or coming back later does not show it again.
    void navigate(location.pathname, { replace: true, state: null })
  }, [notice, showSaved, navigate, location.pathname])

  useEffect(() => {
    let active = true
    listSummaries()
      .then(({ summaries }) => {
        if (active) {
          setLoad({ status: 'loaded', summaries, attempt })
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setLoad({ status: 'failed', message: unexpectedErrorMessage(error), attempt })
        }
      })
    return () => {
      active = false
    }
  }, [attempt])

  return (
    <section className="page summaries-page">
      <SavedMessage phase={saved.phase} count={saved.count}>
        {SUMMARY_DELETED_MESSAGE}
      </SavedMessage>
      <Message className="summaries-page__notice" variant="info">
        {goneShown ? SUMMARY_GONE_ON_DELETE_MESSAGE : null}
      </Message>
      <h1 ref={headingRef} tabIndex={-1}>
        {SUMMARIES_TITLE}
      </h1>
      <div className="summaries-page__content">
        {current.status === 'loading' && (
          <div className="summaries-page__state">
            <p className="summaries-page__loading" role="status">
              <span className="spinner" aria-hidden="true" />
              {LOADING_SUMMARIES_TEXT}
            </p>
            <Message variant="info">{wakingUp ? WAKING_UP_MESSAGE : null}</Message>
          </div>
        )}
        {current.status === 'failed' && (
          <div className="summaries-page__state">
            <Message variant="error">{current.message}</Message>
            <div>
              <Button
                variant="secondary"
                // After a retry fails again, focus goes to the new button, unless the user moved on (#84).
                ref={attempt > 0 ? focusWhenShown : undefined}
                onClick={() => setAttempt((count) => count + 1)}
              >
                Try again
              </Button>
            </div>
          </div>
        )}
        {current.status === 'loaded' && current.summaries.length === 0 && (
          <EmptyState
            action={
              <ButtonLink variant="primary" to="/review">
                {GO_TO_REVIEW_LABEL}
              </ButtonLink>
            }
          >
            {NO_SUMMARIES_TEXT}
          </EmptyState>
        )}
        {current.status === 'loaded' && current.summaries.length > 0 && (
          // In the order the server sends them: newest created first.
          <ul className="summaries-page__list">
            {current.summaries.map((summary) => (
              <li key={summary.id}>
                <SummaryRow summary={summary} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
