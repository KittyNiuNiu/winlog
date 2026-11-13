import { Sparkles } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { NotAuthenticatedError, generateSummary, updateSummary, type Summary } from '../api/index.ts'
import { Button } from '../components/Button.tsx'
import Icon from '../components/Icon.tsx'
import Message from '../components/Message.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import { summaryFilterText } from '../components/summaryFilterText.ts'
import { TextArea } from '../components/TextField.tsx'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import DiscardDialog from '../entries/DiscardDialog.tsx'
import { useLeavePrompt } from '../entries/useLeavePrompt.tsx'
import { filterSearchParams, type ReviewFilter } from './reviewFilter.ts'
import {
  DRAFTING_LABEL,
  DRAFTING_TEXT,
  DRAFT_AGAIN_LABEL,
  DRAFT_LABEL,
  DRAFT_NOTE,
  EMPTY_SUMMARY_TEXT,
  SAVE_SUMMARY_LABEL,
  SAVING_LABEL,
  SUMMARY_FIELD_LABEL,
  SUMMARY_SAVED_TEXT,
  SUMMARY_TITLE,
  draftAgainLine,
  draftAvailability,
  draftLine,
  draftNoticeOf,
  saveErrorOf,
  sourceLine,
  summaryRequest,
} from './summaryDraft.ts'
import './SummaryPanel.css'

interface SummaryPanelProps {
  /** The filter shown on the page: `parseFilter` of the URL. */
  filter: ReviewFilter
  /** The number of entries shown for that filter, or null while they load or after they failed. */
  entryCount: number | null
}

/** Where focus goes once the panel has rendered after a request. */
type FocusTarget = 'source' | 'draft-button' | 'save'

/** Scrolls the window so the panel's top is at the top, only if that edge is outside the window. */
function scrollIntoViewIfNeeded(panel: HTMLElement) {
  const top = panel.getBoundingClientRect().top
  if (top >= 0 && top < window.innerHeight) {
    return
  }
  const reduced =
    typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: window.scrollY + top, behavior: reduced ? 'auto' : 'smooth' })
}

/**
 * The summary panel on the review page (FR-R3 to FR-R5, #32 and its design note). It drafts
 * an AI summary of exactly the entries shown, then shows the draft, which is already saved,
 * for the user to edit and save. Changing the filters never changes the draft in the panel.
 */
export default function SummaryPanel({ filter, entryCount }: SummaryPanelProps) {
  /** The summary in the panel, as last saved (its `text` is the last saved text). */
  const [draft, setDraft] = useState<Summary | null>(null)
  const [text, setText] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  /** Whether Save found the text empty; the message shows while it still is. */
  const [emptyChecked, setEmptyChecked] = useState(false)
  const [confirmingAgain, setConfirmingAgain] = useState(false)
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget } | null>(null)
  const saved = useSavedMessage()
  // Refs answer a second tap before React renders again, so it sends nothing.
  const draftingRef = useRef(false)
  const savingRef = useRef(false)
  const mountedRef = useRef(true)

  const panelRef = useRef<HTMLElement>(null)
  const sourceRef = useRef<HTMLParagraphElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const saveRef = useRef<HTMLButtonElement>(null)
  // "Draft summary" without a draft, "Draft again" with one: never both.
  const draftButtonRef = useRef<HTMLButtonElement>(null)

  const id = useId()
  const titleId = `${id}-title`
  const lineId = `${id}-line`

  const dirty = draft !== null && text !== draft.text
  const leavePrompt = useLeavePrompt(dirty, { allowSamePath: true })

  // A filter change removes a drafting notice (adjusted while rendering, as React suggests).
  const filterKey = filterSearchParams(filter).toString()
  const [noticeFilterKey, setNoticeFilterKey] = useState(filterKey)
  if (noticeFilterKey !== filterKey) {
    setNoticeFilterKey(filterKey)
    setNotice(null)
  }

  useEffect(() => {
    mountedRef.current = true
    // An answer that arrives after the user left /review changes nothing.
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (focusRequest === null) {
      return
    }
    if (focusRequest.target === 'source') {
      // Never the text field, so the phone keyboard does not open.
      sourceRef.current?.focus({ preventScroll: true })
      if (panelRef.current !== null) {
        scrollIntoViewIfNeeded(panelRef.current)
      }
      return
    }
    // A busy button is disabled and may lose focus. Bring it back, unless the user moved on.
    const element = focusRequest.target === 'save' ? saveRef.current : draftButtonRef.current
    const active = document.activeElement
    if (element !== null && (active === null || active === document.body || active === element)) {
      element.focus()
    }
  }, [focusRequest])

  const availability = draftAvailability(filter, entryCount)
  let line: string | null = null
  if (availability.kind === 'hint') {
    line = availability.hint
  } else if (availability.kind === 'ready') {
    line = draft === null ? draftLine(availability.count) : draftAgainLine(availability.count)
  }
  const lineShown = line !== null && !drafting

  async function startDraft() {
    const body = summaryRequest(filter)
    if (body === null || draftingRef.current || savingRef.current) {
      return
    }
    draftingRef.current = true
    setDrafting(true)
    setNotice(null)
    setSaveError(null)
    saved.hide()
    let summary: Summary
    try {
      // The filter at the moment of the tap; later filter changes do not touch it.
      summary = await generateSummary(body)
    } catch (error) {
      if (!mountedRef.current) {
        return
      }
      draftingRef.current = false
      setDrafting(false)
      // An expired login already went to the login page (#25).
      if (!(error instanceof NotAuthenticatedError)) {
        setNotice(draftNoticeOf(error))
      }
      setFocusRequest({ target: 'draft-button' })
      return
    }
    if (!mountedRef.current) {
      return
    }
    draftingRef.current = false
    setDrafting(false)
    setDraft(summary)
    setText(summary.text)
    setEmptyChecked(false)
    setFocusRequest({ target: 'source' })
  }

  function handleDraft() {
    if (draftingRef.current || savingRef.current || availability.kind !== 'ready') {
      return
    }
    if (dirty) {
      setConfirmingAgain(true)
      return
    }
    void startDraft()
  }

  function handleKeepEditing() {
    setConfirmingAgain(false)
    draftButtonRef.current?.focus()
  }

  function handleDiscard() {
    setConfirmingAgain(false)
    if (draft !== null) {
      setText(draft.text)
    }
    void startDraft()
  }

  async function handleSave() {
    if (draft === null || savingRef.current || draftingRef.current) {
      return
    }
    setSaveError(null)
    setNotice(null)
    saved.hide()
    if (text.trim() === '') {
      setEmptyChecked(true)
      textRef.current?.focus()
      return
    }
    savingRef.current = true
    setSaving(true)
    let result: Summary
    try {
      result = await updateSummary(draft.id, { text })
    } catch (error) {
      if (!mountedRef.current) {
        return
      }
      savingRef.current = false
      setSaving(false)
      if (!(error instanceof NotAuthenticatedError)) {
        setSaveError(saveErrorOf(error))
      }
      setFocusRequest({ target: 'save' })
      return
    }
    if (!mountedRef.current) {
      return
    }
    savingRef.current = false
    setSaving(false)
    setDraft(result)
    setText(result.text)
    saved.show()
    setFocusRequest({ target: 'save' })
  }

  const emptyShown = emptyChecked && text.trim() === ''

  return (
    <>
      <section ref={panelRef} className="summary-panel" aria-labelledby={titleId}>
        <h2 id={titleId} className="summary-panel__title">
          {SUMMARY_TITLE}
        </h2>
        <div className="summary-panel__body">
          {draft !== null && (
            <>
              <p ref={sourceRef} className="summary-panel__source" tabIndex={-1}>
                {sourceLine(summaryFilterText(draft.filter))}
              </p>
              <p className="summary-panel__note">{DRAFT_NOTE}</p>
              <div className="summary-panel__field">
                <TextArea
                  id={`${id}-text`}
                  label={SUMMARY_FIELD_LABEL}
                  ref={textRef}
                  value={text}
                  readOnly={saving || drafting}
                  messages={emptyShown ? [EMPTY_SUMMARY_TEXT] : []}
                  onChange={(event) => {
                    if (!savingRef.current && !draftingRef.current) {
                      setText(event.target.value)
                    }
                  }}
                />
              </div>
              <Button
                ref={saveRef}
                variant="primary"
                className="summary-panel__save"
                disabled={drafting}
                busy={saving}
                busyLabel={SAVING_LABEL}
                onClick={() => void handleSave()}
              >
                {SAVE_SUMMARY_LABEL}
              </Button>
            </>
          )}
          <Button
            ref={draftButtonRef}
            variant="secondary"
            className="summary-panel__draft"
            disabled={availability.kind !== 'ready' || saving}
            busy={drafting}
            busyLabel={DRAFTING_LABEL}
            aria-describedby={lineShown ? lineId : undefined}
            onClick={handleDraft}
          >
            <Icon icon={Sparkles} size={20} />
            {draft === null ? DRAFT_LABEL : DRAFT_AGAIN_LABEL}
          </Button>
          {lineShown && (
            <p id={lineId} className="summary-panel__line">
              {line}
            </p>
          )}
          <p className="summary-panel__line summary-panel__progress" role="status">
            {drafting ? DRAFTING_TEXT : null}
          </p>
          <div className="summary-panel__messages">
            <Message variant="info">{notice}</Message>
            <Message variant="error">{saveError}</Message>
            <SavedMessage phase={saved.phase} count={saved.count}>
              {SUMMARY_SAVED_TEXT}
            </SavedMessage>
          </div>
        </div>
      </section>
      <DiscardDialog open={confirmingAgain} onKeepEditing={handleKeepEditing} onDiscard={handleDiscard} />
      {leavePrompt.dialog}
    </>
  )
}
