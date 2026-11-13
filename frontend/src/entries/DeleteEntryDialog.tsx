import { useEffect, useId, useRef, type KeyboardEvent, type SyntheticEvent } from 'react'
import { Button } from '../components/Button.tsx'
import Message from '../components/Message.tsx'
import './DeleteEntryDialog.css'

interface DeleteEntryDialogProps {
  open: boolean
  /** While true, "Delete entry" shows "Deleting…", and neither button nor Escape does anything. */
  busy: boolean
  /** The error of the last attempt, shown in the dialog, or null. */
  error: string | null
  /** Close the dialog and keep the entry. Also Escape. */
  onCancel: () => void
  onDelete: () => void
  /** The question. The entries page's by default; the summary page has its own (#33). */
  title?: string
  /** The text under the question. */
  text?: string
  /** The delete button's label. */
  deleteLabel?: string
}

/**
 * "Delete this entry?" (FR-E4): a native modal dialog with two secondary buttons, as
 * "Discard changes?" (#27), so it adds no filled plum. It opens on "Cancel". After a failed
 * attempt the error shows inside and focus goes to "Delete entry", ready to try again.
 * The summary page (#33) uses it with its own title, text and button label.
 */
export default function DeleteEntryDialog({
  open,
  busy,
  error,
  onCancel,
  onDelete,
  title = 'Delete this entry?',
  text = "This can't be undone.",
  deleteLabel = 'Delete entry',
}: DeleteEntryDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const deleteRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const textId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) {
      return
    }
    if (open && !dialog.open) {
      dialog.showModal()
      cancelRef.current?.focus()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  // The busy button was disabled, so focus left it: put it back for the retry.
  useEffect(() => {
    if (!busy && error !== null) {
      deleteRef.current?.focus()
    }
  }, [busy, error])

  function cancel() {
    if (!busy) {
      onCancel()
    }
  }

  // Escape cancels, except while deleting. The keydown covers every browser; the cancel
  // event covers the browser's own close request.
  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancel()
    }
  }

  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault()
    cancel()
  }

  return (
    <dialog
      ref={dialogRef}
      className="delete-dialog"
      aria-labelledby={titleId}
      aria-describedby={textId}
      onKeyDown={handleKeyDown}
      onCancel={handleCancel}
    >
      <h2 id={titleId}>{title}</h2>
      <p className="delete-dialog__text" id={textId}>
        {text}
      </p>
      <Message className="delete-dialog__error" variant="error">
        {error}
      </Message>
      <div className="delete-dialog__actions">
        <Button ref={cancelRef} variant="secondary" onClick={cancel}>
          Cancel
        </Button>
        <Button ref={deleteRef} variant="secondary" busy={busy} busyLabel="Deleting…" onClick={onDelete}>
          {deleteLabel}
        </Button>
      </div>
    </dialog>
  )
}
