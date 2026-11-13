import { Copy, Trash2 } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  NotAuthenticatedError,
  NotFoundError,
  ValidationError,
  deleteSummary,
  getSummary,
  updateSummary,
  type Summary,
} from '../api/index.ts'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { Button } from '../components/Button.tsx'
import Icon from '../components/Icon.tsx'
import Message from '../components/Message.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import {
  EMPTY_SUMMARY_TEXT,
  SAVE_SUMMARY_LABEL,
  SAVING_LABEL,
  SUMMARY_FIELD_LABEL,
  SUMMARY_SAVED_TEXT,
  saveErrorOf,
  sourceLine,
} from '../components/summaryEditor.ts'
import { summaryFilterText } from '../components/summaryFilterText.ts'
import { TextArea } from '../components/TextField.tsx'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import DeleteEntryDialog from '../entries/DeleteEntryDialog.tsx'
import { useLeavePrompt } from '../entries/useLeavePrompt.tsx'
import { summaryDeletedState, type SummaryDeletedNotice } from '../summaries/summaryDeletedNotice.ts'
import {
  BACK_TO_SUMMARIES,
  COPIED_LABEL,
  COPIED_MS,
  COPY_FAILED_MESSAGE,
  COPY_LABEL,
  DELETE_LABEL,
  DELETE_SUMMARY_LABEL,
  DELETE_SUMMARY_TEXT,
  DELETE_SUMMARY_TITLE,
  EDIT_NOTE,
  LOADING_SUMMARY_TEXT,
  SUMMARY_MISSING_MESSAGE,
  SUMMARY_PAGE_TITLE,
  createdLine,
} from '../summaries/summaryTexts.ts'
import './SummaryPage.css'

const SUMMARIES_PATH = '/summaries'

type Load =
  | { status: 'loading' }
  | { status: 'loaded'; summary: Summary }
  | { status: 'missing' }
  | { status: 'failed'; message: string }

/** `not_found`, or an id that is not a valid summary id: the summary "doesn't exist". */
function isMissing(error: unknown): boolean {
  return (
    error instanceof NotFoundError ||
    (error instanceof ValidationError && error.fields.some(({ field }) => field === 'summaryId'))
  )
}

/** Puts `text` on the clipboard as plain text. Rejects when the browser refuses or has no Clipboard API. */
async function copyToClipboard(text: string): Promise<void> {
  // TypeScript says the Clipboard API is always there; it is not outside secure contexts.
  const clipboard = (navigator as Partial<Navigator>).clipboard
  if (clipboard === undefined || typeof clipboard.writeText !== 'function') {
    throw new Error('The Clipboard API is not available.')
  }
  await clipboard.writeText(text)
}

/** Where focus goes once the page has rendered after an action. */
type FocusTarget = 'save' | 'delete'

/** The delete dialog while it is open, and how the delete is going. */
interface Confirm {
  busy: boolean
  error: string | null
}

/** An error in the message slot, and which action it came from. */
interface SlotError {
  from: 'save' | 'copy'
  text: string
}

/**
 * One saved summary: its source and creation lines, the always editable text with Save
 * summary, Copy and Delete (FR-R5, FR-R6, #33 and its design note). Editing changes only
 * the summary, never an entry (§7.4).
 */
function SummaryEditor({ summary }: { summary: Summary }) {
  const navigate = useNavigate()
  /** The summary as last saved. */
  const [stored, setStored] = useState(summary)
  const [text, setText] = useState(summary.text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<SlotError | null>(null)
  /** Whether Save found the text empty; the message shows while it still is. */
  const [emptyChecked, setEmptyChecked] = useState(false)
  const [copied, setCopied] = useState(false)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget } | null>(null)
  const saved = useSavedMessage()
  // Refs answer a second tap before React renders again, so it sends nothing.
  const savingRef = useRef(false)
  const deletingRef = useRef(false)
  const mountedRef = useRef(true)
  const copiedTimer = useRef<number | null>(null)

  const textRef = useRef<HTMLTextAreaElement>(null)
  const saveRef = useRef<HTMLButtonElement>(null)
  const deleteRef = useRef<HTMLButtonElement>(null)

  const id = useId()
  const dirty = text !== stored.text
  const leavePrompt = useLeavePrompt(dirty)
  const blank = text.trim() === ''

  useEffect(() => {
    mountedRef.current = true
    // An answer that arrives after the user left changes nothing.
    return () => {
      mountedRef.current = false
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current)
      }
    }
  }, [])

  // Runs after the dialog has closed (a child's effects run first), so the dialog does not
  // take focus back.
  useEffect(() => {
    if (focusRequest === null) {
      return
    }
    if (focusRequest.target === 'delete') {
      // The dialog was closed with Cancel or Escape: back to the button that opened it.
      deleteRef.current?.focus()
      return
    }
    // The busy button was disabled and may have lost focus. Bring it back, unless the user
    // moved on.
    const element = saveRef.current
    const active = document.activeElement
    if (element !== null && (active === null || active === document.body || active === element)) {
      element.focus()
    }
  }, [focusRequest])

  async function handleSave() {
    if (savingRef.current) {
      return
    }
    setError(null)
    saved.hide()
    if (blank) {
      setEmptyChecked(true)
      textRef.current?.focus()
      return
    }
    savingRef.current = true
    setSaving(true)
    let result: Summary
    try {
      // Exactly as typed.
      result = await updateSummary(stored.id, { text })
    } catch (failure) {
      if (!mountedRef.current) {
        return
      }
      savingRef.current = false
      setSaving(false)
      // An expired login already went to the login page (#25).
      if (!(failure instanceof NotAuthenticatedError)) {
        setError({ from: 'save', text: saveErrorOf(failure) })
      }
      setFocusRequest({ target: 'save' })
      return
    }
    if (!mountedRef.current) {
      return
    }
    savingRef.current = false
    setSaving(false)
    setStored(result)
    setText(result.text)
    saved.show()
    setFocusRequest({ target: 'save' })
  }

  async function handleCopy() {
    if (blank) {
      return
    }
    setError((current) => (current?.from === 'copy' ? null : current))
    try {
      // The text in the field, unsaved edits included: what the user sees.
      await copyToClipboard(text)
    } catch {
      if (!mountedRef.current) {
        return
      }
      if (copiedTimer.current !== null) {
        window.clearTimeout(copiedTimer.current)
        copiedTimer.current = null
      }
      setCopied(false)
      setError({ from: 'copy', text: COPY_FAILED_MESSAGE })
      return
    }
    if (!mountedRef.current) {
      return
    }
    setCopied(true)
    if (copiedTimer.current !== null) {
      window.clearTimeout(copiedTimer.current)
    }
    copiedTimer.current = window.setTimeout(() => {
      copiedTimer.current = null
      setCopied(false)
    }, COPIED_MS)
  }

  function openDeleteDialog() {
    if (savingRef.current) {
      return
    }
    setConfirm({ busy: false, error: null })
  }

  function closeDeleteDialog() {
    setConfirm(null)
    setFocusRequest({ target: 'delete' })
  }

  /** Back to the list, which shows `notice` once. Never asks "Discard changes?". */
  function leaveAfterDelete(notice: SummaryDeletedNotice) {
    leavePrompt.allowLeaving()
    // The deleted page is replaced, so Back does not return to it.
    void navigate(SUMMARIES_PATH, { replace: true, state: summaryDeletedState(notice) })
  }

  async function handleDelete() {
    if (deletingRef.current) {
      return
    }
    deletingRef.current = true
    setConfirm({ busy: true, error: null })
    try {
      await deleteSummary(stored.id)
    } catch (failure) {
      deletingRef.current = false
      if (!mountedRef.current) {
        return
      }
      if (failure instanceof NotFoundError) {
        leaveAfterDelete('gone')
      } else if (!(failure instanceof NotAuthenticatedError)) {
        // The dialog moves focus to "Delete summary" for a retry.
        setConfirm({ busy: false, error: unexpectedErrorMessage(failure) })
      }
      return
    }
    deletingRef.current = false
    if (mountedRef.current) {
      leaveAfterDelete('deleted')
    }
  }

  const emptyShown = emptyChecked && blank

  return (
    <>
      <p className="summary-page__source">{sourceLine(summaryFilterText(stored.filter))}</p>
      <p className="summary-page__created">{createdLine(stored.created_at)}</p>
      <div className="summary-page__field">
        <TextArea
          id={`${id}-text`}
          label={SUMMARY_FIELD_LABEL}
          hint={EDIT_NOTE}
          ref={textRef}
          value={text}
          readOnly={saving}
          messages={emptyShown ? [EMPTY_SUMMARY_TEXT] : []}
          onChange={(event) => {
            if (!savingRef.current) {
              setText(event.target.value)
            }
          }}
        />
      </div>
      <div className="summary-page__actions">
        <Button
          ref={saveRef}
          variant="primary"
          className="summary-page__save"
          busy={saving}
          busyLabel={SAVING_LABEL}
          onClick={() => void handleSave()}
        >
          {SAVE_SUMMARY_LABEL}
        </Button>
        <Button variant="secondary" disabled={blank} onClick={() => void handleCopy()}>
          <Icon icon={Copy} size={20} />
          {copied ? COPIED_LABEL : COPY_LABEL}
        </Button>
        <Button
          ref={deleteRef}
          variant="secondary"
          className="summary-page__delete"
          disabled={saving}
          onClick={openDeleteDialog}
        >
          <Icon icon={Trash2} size={20} />
          {DELETE_LABEL}
        </Button>
      </div>
      <div className="summary-page__messages">
        <SavedMessage phase={saved.phase} count={saved.count}>
          {SUMMARY_SAVED_TEXT}
        </SavedMessage>
        <Message variant="error">{error?.text ?? null}</Message>
      </div>
      {/* Screen readers hear "Copied" without focus leaving the button. */}
      <p className="visually-hidden" role="status">
        {copied ? COPIED_LABEL : null}
      </p>
      <DeleteEntryDialog
        open={confirm !== null}
        busy={confirm?.busy ?? false}
        error={confirm?.error ?? null}
        title={DELETE_SUMMARY_TITLE}
        text={DELETE_SUMMARY_TEXT}
        deleteLabel={DELETE_SUMMARY_LABEL}
        onCancel={closeDeleteDialog}
        onDelete={() => void handleDelete()}
      />
      {leavePrompt.dialog}
    </>
  )
}

// One saved summary (FR-R5, FR-R6). A summary that does not exist, belongs to another
// user or has an invalid id shows "This summary doesn't exist.", as the edit entry page.
export default function SummaryPage() {
  const { id = '' } = useParams()
  const [attempt, setAttempt] = useState(0)
  const [load, setLoad] = useState<Load & { key: string }>({ status: 'loading', key: '' })
  const loadKey = `${id}#${attempt}`
  // A new id or a new attempt starts loading again.
  const current: Load = load.key === loadKey ? load : { status: 'loading' }
  const wakingUp = useWakingUpHint(current.status === 'loading')

  useEffect(() => {
    let active = true
    getSummary(id)
      .then((summary) => {
        if (active) {
          setLoad({ status: 'loaded', summary, key: loadKey })
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

  return (
    <section className="page summary-page">
      {/* The not-found message has its own link, so the page has one back link. */}
      {current.status !== 'missing' && (
        <Link className="summary-page__back" to={SUMMARIES_PATH}>
          {BACK_TO_SUMMARIES}
        </Link>
      )}
      <h1>{SUMMARY_PAGE_TITLE}</h1>
      {current.status === 'loading' && (
        <div className="summary-page__state">
          <p className="summary-page__loading" role="status">
            <span className="spinner" aria-hidden="true" />
            {LOADING_SUMMARY_TEXT}
          </p>
          <Message variant="info">{wakingUp ? WAKING_UP_MESSAGE : null}</Message>
        </div>
      )}
      {current.status === 'failed' && (
        <div className="summary-page__state">
          <Message variant="error">{current.message}</Message>
          <div>
            <Button variant="secondary" onClick={() => setAttempt((count) => count + 1)}>
              Try again
            </Button>
          </div>
        </div>
      )}
      {current.status === 'missing' && (
        <Message variant="info">
          {SUMMARY_MISSING_MESSAGE} <Link to={SUMMARIES_PATH}>{BACK_TO_SUMMARIES}</Link>
        </Message>
      )}
      {current.status === 'loaded' && <SummaryEditor key={loadKey} summary={current.summary} />}
    </section>
  )
}
