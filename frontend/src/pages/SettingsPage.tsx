import { Download, Trash2 } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import {
  DemoAccountNotDeletableError,
  NotAuthenticatedError,
  ValidationError,
  WrongPasswordError,
  deleteAccount,
  exportJson,
  exportMarkdown,
  getSession,
  type DownloadedFile,
} from '../api/index.ts'
import { PasswordField } from '../auth/AuthFields.tsx'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { LOGIN_PATH, accountDeletedState } from '../auth/wantedPage.ts'
import { Button } from '../components/Button.tsx'
import Icon from '../components/Icon.tsx'
import Message from '../components/Message.tsx'
import { TextField } from '../components/TextField.tsx'
import { saveFile } from '../settings/saveFile.ts'
import {
  ACCOUNT_HEADING,
  ACCOUNT_TEXT,
  CANCEL_LABEL,
  CONFIRM_LABEL,
  CURRENT_PASSWORD_LABEL,
  DELETE_ACCOUNT_LABEL,
  DELETE_MY_ACCOUNT_LABEL,
  DELETE_STEP_DOWNLOAD_TEXT,
  DELETE_STEP_TEXT,
  DELETE_STEP_TITLE,
  DELETING_LABEL,
  DEMO_ACCOUNT_TEXT,
  DOWNLOADING_LABEL,
  DOWNLOAD_JSON_LABEL,
  DOWNLOAD_MARKDOWN_LABEL,
  SETTINGS_PAGE_TITLE,
  WRONG_PASSWORD_MESSAGE,
  YOUR_DATA_HEADING,
  YOUR_DATA_TEXT,
  isConfirmWord,
} from '../settings/settingsTexts.ts'
import '../auth/AuthForm.css'
import './SettingsPage.css'

type ExportFormat = 'json' | 'markdown'

const EXPORTS: Record<ExportFormat, { label: string; load: () => Promise<DownloadedFile> }> = {
  json: { label: DOWNLOAD_JSON_LABEL, load: exportJson },
  markdown: { label: DOWNLOAD_MARKDOWN_LABEL, load: exportMarkdown },
}

/** The two places with download buttons: "Your data" and the confirmation step. */
type DownloadPlace = 'data' | 'step'

/** The one download message slot: under the pair of buttons the user last pressed. */
interface DownloadSlot {
  place: DownloadPlace
  error: string | null
}

/** Where focus goes once the page has rendered after an action. */
type FocusTarget = 'step' | 'delete' | 'password'

/** The confirmation step's fields and how the deletion is going. */
interface DeleteStep {
  password: string
  confirmation: string
  deleting: boolean
  wrongPassword: boolean
  error: string | null
}

const EMPTY_STEP: DeleteStep = { password: '', confirmation: '', deleting: false, wrongPassword: false, error: null }

/** The step's message for a failed deletion that is not a wrong password. */
function deleteErrorMessage(error: unknown): string | null {
  // An expired login already went to the login page (#25).
  if (error instanceof NotAuthenticatedError) {
    return null
  }
  // 409 `demo_account_not_deletable`, for example from a session without the demo flag.
  if (error instanceof DemoAccountNotDeletableError) {
    return DEMO_ACCOUNT_TEXT
  }
  return unexpectedErrorMessage(error)
}

/** `wrong_password`, or a validation error that names the password (for example too long). */
function isWrongPassword(error: unknown): boolean {
  return (
    error instanceof WrongPasswordError ||
    (error instanceof ValidationError && error.fields.some(({ field }) => field === 'current_password'))
  )
}

interface DownloadButtonsProps {
  place: DownloadPlace
  busy: Record<ExportFormat, boolean>
  disabled: boolean
  slot: DownloadSlot
  wakingUp: boolean
  onDownload: (format: ExportFormat, place: DownloadPlace) => void
}

/** "Download JSON" and "Download Markdown", with the download messages when they belong here. */
function DownloadButtons({ place, busy, disabled, slot, wakingUp, onDownload }: DownloadButtonsProps) {
  const here = slot.place === place
  return (
    <>
      <div className="settings-page__buttons">
        {(Object.keys(EXPORTS) as ExportFormat[]).map((format) => (
          <Button
            key={format}
            variant="secondary"
            busy={busy[format]}
            busyLabel={DOWNLOADING_LABEL}
            disabled={disabled}
            onClick={() => onDownload(format, place)}
          >
            <Icon icon={Download} size={20} />
            {EXPORTS[format].label}
          </Button>
        ))}
      </div>
      <div className="settings-page__messages">
        <Message variant="error">{here ? slot.error : null}</Message>
        <Message variant="info">{here && wakingUp ? WAKING_UP_MESSAGE : null}</Message>
      </div>
    </>
  )
}

// Data and account settings (FR-D1, FR-D2, design note on #34): download all entries and
// summaries as JSON or Markdown, and delete the account after a confirmation step in the
// page. Logging out stays in the navigation (FR-A2). Every button is secondary. The demo
// account cannot be deleted (FR-X1), so its Account section has one sentence only.
export default function SettingsPage() {
  const navigate = useNavigate()
  const id = useId()
  const demo = getSession()?.demo === true

  const [downloading, setDownloading] = useState<Record<ExportFormat, boolean>>({ json: false, markdown: false })
  const [downloadSlot, setDownloadSlot] = useState<DownloadSlot>({ place: 'data', error: null })
  const [step, setStep] = useState<DeleteStep | null>(null)
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget } | null>(null)
  const downloadWakingUp = useWakingUpHint(downloading.json || downloading.markdown)
  const deleting = step?.deleting ?? false
  const deleteWakingUp = useWakingUpHint(deleting)

  // Refs answer a second tap before React renders again, so it sends nothing.
  const downloadingRef = useRef<Record<ExportFormat, boolean>>({ json: false, markdown: false })
  const deletingRef = useRef(false)
  const mountedRef = useRef(true)

  const stepTitleRef = useRef<HTMLHeadingElement>(null)
  const deleteAccountRef = useRef<HTMLButtonElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    mountedRef.current = true
    // An answer that arrives after the user left changes nothing on this page.
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (focusRequest === null) {
      return
    }
    const element = {
      step: stepTitleRef.current,
      delete: deleteAccountRef.current,
      password: passwordRef.current,
    }[focusRequest.target]
    element?.focus()
  }, [focusRequest])

  async function handleDownload(format: ExportFormat, place: DownloadPlace) {
    if (downloadingRef.current[format] || deletingRef.current) {
      return
    }
    downloadingRef.current[format] = true
    setDownloading((current) => ({ ...current, [format]: true }))
    setDownloadSlot({ place, error: null })
    try {
      const file = await EXPORTS[format].load()
      if (mountedRef.current) {
        saveFile(file)
      }
    } catch (failure) {
      // An expired login already went to the login page (#25).
      if (mountedRef.current && !(failure instanceof NotAuthenticatedError)) {
        setDownloadSlot((current) => ({ ...current, error: unexpectedErrorMessage(failure) }))
      }
    } finally {
      downloadingRef.current[format] = false
      if (mountedRef.current) {
        setDownloading((current) => ({ ...current, [format]: false }))
      }
    }
  }

  function openStep() {
    setStep(EMPTY_STEP)
    setFocusRequest({ target: 'step' })
  }

  function cancelStep() {
    if (deletingRef.current) {
      return
    }
    // The step unmounts, so its fields empty and the password is hidden again.
    setStep(null)
    // A download message shown in the step moves to "Your data", so it is not lost.
    setDownloadSlot((current) => ({ ...current, place: 'data' }))
    setFocusRequest({ target: 'delete' })
  }

  function changeStep(change: Partial<DeleteStep>) {
    if (deletingRef.current) {
      return
    }
    setStep((current) => (current === null ? current : { ...current, ...change }))
  }

  async function handleDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (step === null || deletingRef.current || step.password === '' || !isConfirmWord(step.confirmation)) {
      return
    }
    deletingRef.current = true
    setStep({ ...step, deleting: true, wrongPassword: false, error: null })
    try {
      // Exactly as typed: no trimming.
      await deleteAccount({ current_password: step.password })
    } catch (failure) {
      deletingRef.current = false
      if (!mountedRef.current) {
        return
      }
      if (isWrongPassword(failure)) {
        setStep((current) => current && { ...current, deleting: false, wrongPassword: true })
        setFocusRequest({ target: 'password' })
      } else {
        // The rest can be tried again.
        const error = deleteErrorMessage(failure)
        setStep((current) => current && { ...current, deleting: false, error })
      }
      return
    }
    deletingRef.current = false
    // The session is gone (deleteAccount removed it). /login replaces /settings, so Back
    // does not return to it.
    void navigate(LOGIN_PATH, { replace: true, state: accountDeletedState() })
  }

  const downloadProps = {
    busy: downloading,
    disabled: deleting,
    slot: downloadSlot,
    wakingUp: downloadWakingUp,
    onDownload: (format: ExportFormat, place: DownloadPlace) => void handleDownload(format, place),
  }
  const ready = step !== null && step.password !== '' && isConfirmWord(step.confirmation)

  return (
    <section className="page settings-page">
      <h1>{SETTINGS_PAGE_TITLE}</h1>

      <section className="settings-page__section" aria-labelledby={`${id}-data`}>
        <h2 id={`${id}-data`}>{YOUR_DATA_HEADING}</h2>
        <p className="settings-page__text">{YOUR_DATA_TEXT}</p>
        <DownloadButtons place="data" {...downloadProps} />
      </section>

      <section className="settings-page__section" aria-labelledby={`${id}-account`}>
        <h2 id={`${id}-account`}>{ACCOUNT_HEADING}</h2>
        <p className="settings-page__text">{demo ? DEMO_ACCOUNT_TEXT : ACCOUNT_TEXT}</p>
        {demo ? null : step === null ? (
          <div className="settings-page__buttons">
            <Button ref={deleteAccountRef} variant="secondary" onClick={openStep}>
              <Icon icon={Trash2} size={20} />
              {DELETE_ACCOUNT_LABEL}
            </Button>
          </div>
        ) : (
          <section className="settings-page__step" aria-labelledby={`${id}-step`}>
            <h3 className="settings-page__step-title" id={`${id}-step`} ref={stepTitleRef} tabIndex={-1}>
              {DELETE_STEP_TITLE}
            </h3>
            <p className="settings-page__step-text">{DELETE_STEP_TEXT}</p>
            <p className="settings-page__step-text">{DELETE_STEP_DOWNLOAD_TEXT}</p>
            <DownloadButtons place="step" {...downloadProps} />
            <form className="settings-page__form" noValidate onSubmit={(event) => void handleDelete(event)}>
              <PasswordField
                id={`${id}-password`}
                label={CURRENT_PASSWORD_LABEL}
                autoComplete="current-password"
                value={step.password}
                readOnly={deleting}
                inputRef={passwordRef}
                messages={step.wrongPassword ? [WRONG_PASSWORD_MESSAGE] : []}
                onChange={(password) => changeStep({ password, wrongPassword: false })}
              />
              <TextField
                id={`${id}-confirm`}
                label={CONFIRM_LABEL}
                type="text"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                value={step.confirmation}
                readOnly={deleting}
                onChange={(event) => changeStep({ confirmation: event.target.value })}
              />
              <div className="settings-page__buttons settings-page__step-actions">
                <Button variant="secondary" disabled={deleting} onClick={cancelStep}>
                  {CANCEL_LABEL}
                </Button>
                <Button
                  variant="secondary"
                  type="submit"
                  disabled={!ready}
                  busy={deleting}
                  busyLabel={DELETING_LABEL}
                >
                  <Icon icon={Trash2} size={20} />
                  {DELETE_MY_ACCOUNT_LABEL}
                </Button>
              </div>
              <div className="settings-page__messages">
                <Message variant="error">{step.error}</Message>
                <Message variant="info">{deleteWakingUp ? WAKING_UP_MESSAGE : null}</Message>
              </div>
            </form>
          </section>
        )}
      </section>
    </section>
  )
}
