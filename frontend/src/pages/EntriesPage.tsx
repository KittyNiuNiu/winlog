import { useEffect, useId, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { NotFoundError, deleteEntry, listEntries, type Entry } from '../api/index.ts'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { Button, ButtonLink } from '../components/Button.tsx'
import EmptyState from '../components/EmptyState.tsx'
import EntryRow from '../components/EntryRow.tsx'
import { formatMonthHeading } from '../components/formatDate.ts'
import Message from '../components/Message.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import { LAPTOP_QUERY, useMediaQuery } from '../components/useMediaQuery.ts'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import DeleteEntryDialog from '../entries/DeleteEntryDialog.tsx'
import { cameFromEntrySave } from '../entries/entrySavedNotice.ts'
import { ENTRY_DELETED_MESSAGE, ENTRY_GONE_ON_DELETE_MESSAGE, ENTRY_SAVED_MESSAGE } from '../entries/entryTexts.ts'
import './EntriesPage.css'

type Load =
  | { status: 'loading' }
  | { status: 'loaded'; entries: Entry[] }
  | { status: 'failed'; message: string }

/** The entry the delete dialog is open for, and how the delete is going. */
interface Confirm {
  entry: Entry
  busy: boolean
  error: string | null
}

/** Where keyboard focus goes after the next render. */
type FocusTarget = { kind: 'edit' | 'delete'; id: string } | { kind: 'empty' }

interface MonthGroup {
  /** "YYYY-MM" */
  key: string
  heading: string
  entries: Entry[]
}

/**
 * The entries split into months, in the order they come. The API sorts by date, newest
 * first, so each month is one run of entries and the page does not sort again.
 */
function groupByMonth(entries: Entry[]): MonthGroup[] {
  const groups: MonthGroup[] = []
  for (const entry of entries) {
    const key = entry.date.slice(0, 7)
    const last = groups.at(-1)
    if (last !== undefined && last.key === key) {
      last.entries.push(entry)
    } else {
      groups.push({ key, heading: formatMonthHeading(entry.date), entries: [entry] })
    }
  }
  return groups
}

// All of the user's entries, grouped by month, with Edit and Delete on each (FR-E4). After
// saving an edit, it shows "Entry saved." at the top once (#27).
export default function EntriesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const laptop = useMediaQuery(LAPTOP_QUERY)
  const saved = useSavedMessage()
  const { show: showSaved, hide: hideSaved } = saved
  // The text of the saved band ("Entry saved." or "Entry deleted.").
  const [savedText, setSavedText] = useState(ENTRY_SAVED_MESSAGE)
  // "This entry was already deleted." stays until another message replaces it.
  const [goneShown, setGoneShown] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [load, setLoad] = useState<Load & { attempt: number }>({ status: 'loading', attempt: 0 })
  // A new attempt starts loading again.
  const current: Load = load.attempt === attempt ? load : { status: 'loading' }
  const wakingUp = useWakingUpHint(current.status === 'loading')
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const deleting = useRef(false)
  // Where focus goes once the next render is on screen.
  const focusTarget = useRef<FocusTarget | null>(null)
  const editLinks = useRef(new Map<string, HTMLAnchorElement>())
  const deleteButtons = useRef(new Map<string, HTMLButtonElement>())
  const emptyRef = useRef<HTMLDivElement>(null)
  const headingIdPrefix = useId()
  const fromSave = cameFromEntrySave(location.state)

  useEffect(() => {
    if (!fromSave) {
      return
    }
    // The page has just opened, so no other message shows and the band says "Entry saved.".
    showSaved()
    // Forget it, so a reload or coming back later does not show it again.
    void navigate(location.pathname, { replace: true, state: null })
  }, [fromSave, showSaved, navigate, location.pathname])

  useEffect(() => {
    let active = true
    listEntries()
      .then(({ entries }) => {
        if (active) {
          setLoad({ status: 'loaded', entries, attempt })
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

  // After every render. It runs after the dialog has closed (a child's effects run first),
  // so the dialog does not take focus back.
  useEffect(() => {
    const target = focusTarget.current
    if (target === null) {
      return
    }
    focusTarget.current = null
    let element: HTMLElement | null | undefined
    if (target.kind === 'edit') {
      element = editLinks.current.get(target.id)
    } else if (target.kind === 'delete') {
      element = deleteButtons.current.get(target.id)
    } else {
      element = emptyRef.current?.querySelector('a')
    }
    element?.focus()
  })

  function closeDialog() {
    if (confirm === null) {
      return
    }
    focusTarget.current = { kind: 'delete', id: confirm.entry.id }
    setConfirm(null)
  }

  /** Removes the deleted row, without loading the list again, and shows its message. */
  function removeEntry(id: string, gone: boolean) {
    const entries = current.status === 'loaded' ? current.entries : []
    const index = entries.findIndex((entry) => entry.id === id)
    const rest = entries.filter((entry) => entry.id !== id)
    // The row that takes its place, or the row above it when it was the last one.
    const next = rest[Math.min(index, rest.length - 1)]
    setLoad({ status: 'loaded', entries: rest, attempt })
    setConfirm(null)
    focusTarget.current = next === undefined ? { kind: 'empty' } : { kind: 'edit', id: next.id }
    if (gone) {
      hideSaved()
      setGoneShown(true)
    } else {
      setGoneShown(false)
      setSavedText(ENTRY_DELETED_MESSAGE)
      showSaved()
    }
  }

  async function handleDelete() {
    if (confirm === null || deleting.current) {
      return
    }
    const { entry } = confirm
    deleting.current = true
    setConfirm({ entry, busy: true, error: null })
    try {
      await deleteEntry(entry.id)
      removeEntry(entry.id, false)
    } catch (error) {
      if (error instanceof NotFoundError) {
        removeEntry(entry.id, true)
      } else {
        // An expired login has already sent the user to the login page (#25).
        setConfirm({ entry, busy: false, error: unexpectedErrorMessage(error) })
      }
    } finally {
      deleting.current = false
    }
  }

  const empty = current.status === 'loaded' && current.entries.length === 0

  return (
    <section className="page entries-page">
      <SavedMessage phase={saved.phase} count={saved.count}>
        {savedText}
      </SavedMessage>
      <Message className="entries-page__notice" variant="info">
        {goneShown ? ENTRY_GONE_ON_DELETE_MESSAGE : null}
      </Message>
      <h1>Entries</h1>
      {/* On the laptop, the sidebar's "New entry" is always in view (#75). */}
      {!laptop && !empty && (
        <div className="entries-page__new">
          <ButtonLink variant="primary" to="/entries/new">
            New entry
          </ButtonLink>
        </div>
      )}
      <div className="entries-page__content">
        {current.status === 'loading' && (
          <div className="entries-page__state">
            <p className="entries-page__loading" role="status">
              <span className="spinner" aria-hidden="true" />
              Loading entries…
            </p>
            <Message variant="info">{wakingUp ? WAKING_UP_MESSAGE : null}</Message>
          </div>
        )}
        {current.status === 'failed' && (
          <div className="entries-page__state">
            <Message variant="error">{current.message}</Message>
            <div>
              <Button variant="secondary" onClick={() => setAttempt((count) => count + 1)}>
                Try again
              </Button>
            </div>
          </div>
        )}
        {empty && (
          <div ref={emptyRef}>
            <EmptyState
              action={
                <ButtonLink variant="primary" to="/entries/new">
                  New entry
                </ButtonLink>
              }
            >
              No entries yet. Write your first win.
            </EmptyState>
          </div>
        )}
        {current.status === 'loaded' &&
          groupByMonth(current.entries).map((group) => {
            const headingId = `${headingIdPrefix}-${group.key}`
            return (
              <section className="entries-page__month" key={group.key} aria-labelledby={headingId}>
                <h2 id={headingId}>{group.heading}</h2>
                <ul className="entries-page__list">
                  {group.entries.map((entry) => (
                    <li key={entry.id}>
                      <EntryRow
                        entry={entry}
                        tags={entry.tags}
                        actions={{
                          editTo: `/entries/${entry.id}/edit`,
                          onDelete: () => setConfirm({ entry, busy: false, error: null }),
                        }}
                        editRef={(element) => {
                          setRef(editLinks.current, entry.id, element)
                        }}
                        deleteRef={(element) => {
                          setRef(deleteButtons.current, entry.id, element)
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
      </div>
      <DeleteEntryDialog
        open={confirm !== null}
        busy={confirm?.busy ?? false}
        error={confirm?.error ?? null}
        onCancel={closeDialog}
        onDelete={() => void handleDelete()}
      />
    </section>
  )
}

function setRef<T>(map: Map<string, T>, id: string, element: T | null) {
  if (element === null) {
    map.delete(id)
  } else {
    map.set(id, element)
  }
}
