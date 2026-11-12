import { useEffect, useId, useRef, type KeyboardEvent, type SyntheticEvent } from 'react'
import { Button } from '../components/Button.tsx'
import './DiscardDialog.css'

interface DiscardDialogProps {
  open: boolean
  /** Stay on the page; everything is kept. Also Escape. */
  onKeepEditing: () => void
  /** Leave the page; nothing is saved. */
  onDiscard: () => void
}

/**
 * "Discard changes?": a native modal dialog with two secondary buttons, so Save entry
 * stays the screen's only filled plum element. It opens on "Keep editing".
 */
export default function DiscardDialog({ open, onKeepEditing, onDiscard }: DiscardDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const keepRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const textId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) {
      return
    }
    if (open && !dialog.open) {
      dialog.showModal()
      keepRef.current?.focus()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  // Escape keeps editing. The keydown covers every browser; the cancel event covers the
  // browser's own close request.
  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onKeepEditing()
    }
  }

  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault()
    onKeepEditing()
  }

  return (
    <dialog
      ref={dialogRef}
      className="discard-dialog"
      aria-labelledby={titleId}
      aria-describedby={textId}
      onKeyDown={handleKeyDown}
      onCancel={handleCancel}
    >
      <h2 id={titleId}>Discard changes?</h2>
      <p className="discard-dialog__text" id={textId}>
        Your changes haven&apos;t been saved.
      </p>
      <div className="discard-dialog__actions">
        <Button ref={keepRef} variant="secondary" onClick={onKeepEditing}>
          Keep editing
        </Button>
        <Button variant="secondary" onClick={onDiscard}>
          Discard
        </Button>
      </div>
    </dialog>
  )
}
