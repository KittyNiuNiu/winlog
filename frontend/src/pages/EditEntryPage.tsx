import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { NotFoundError, ValidationError, getEntry, type Entry } from '../api/index.ts'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { Button } from '../components/Button.tsx'
import { focusWhenShown } from '../components/focus.ts'
import Message from '../components/Message.tsx'
import EntryForm from '../entries/EntryForm.tsx'
import { entrySavedState } from '../entries/entrySavedNotice.ts'
import { ENTRY_MISSING_MESSAGE } from '../entries/entryTexts.ts'
import { useKnownTags } from '../entries/useKnownTags.ts'
import '../entries/EntryForm.css'

type Load =
  | { status: 'loading' }
  | { status: 'loaded'; entry: Entry }
  | { status: 'missing' }
  | { status: 'failed'; message: string }

/** `not_found`, or an id that is not a valid entry id: the entry "doesn't exist". */
function isMissing(error: unknown): boolean {
  return (
    error instanceof NotFoundError ||
    (error instanceof ValidationError && error.fields.some(({ field }) => field === 'entryId'))
  )
}

// Edit one entry (FR-E4). Saving replaces the whole entry (#10) and goes to `/`, which
// shows "Entry saved." once.
export default function EditEntryPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [knownTags] = useKnownTags()
  const [attempt, setAttempt] = useState(0)
  const [load, setLoad] = useState<Load & { key: string }>({ status: 'loading', key: '' })
  const loadKey = `${id}#${attempt}`
  // A new id or a new attempt starts loading again.
  const current: Load = load.key === loadKey ? load : { status: 'loading' }
  const wakingUp = useWakingUpHint(current.status === 'loading')

  useEffect(() => {
    let active = true
    getEntry(id)
      .then((entry) => {
        if (active) {
          setLoad({ status: 'loaded', entry, key: loadKey })
        }
      })
      .catch((error: unknown) => {
        if (!active) {
          return
        }
        setLoad(
          isMissing(error)
            ? { status: 'missing', key: loadKey }
            : { status: 'failed', message: unexpectedErrorMessage(error), key: loadKey },
        )
      })
    return () => {
      active = false
    }
  }, [id, loadKey])

  function handleSaved() {
    void navigate('/', { state: entrySavedState() })
  }

  return (
    <section className="page entry-page">
      <h1>Edit entry</h1>
      {current.status === 'loading' && (
        <div className="entry-page__state">
          <p className="entry-page__loading" role="status">
            <span className="spinner" aria-hidden="true" />
            Loading entry…
          </p>
          <Message variant="info">{wakingUp ? WAKING_UP_MESSAGE : null}</Message>
        </div>
      )}
      {current.status === 'failed' && (
        <div className="entry-page__state">
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
      {current.status === 'missing' && (
        <Message variant="info">
          {ENTRY_MISSING_MESSAGE} <Link to="/">Back to entries</Link>
        </Message>
      )}
      {current.status === 'loaded' && (
        <EntryForm
          key={loadKey}
          entry={current.entry}
          knownTags={knownTags}
          onSaved={handleSaved}
          onCancel={() => void navigate('/')}
        />
      )}
    </section>
  )
}
