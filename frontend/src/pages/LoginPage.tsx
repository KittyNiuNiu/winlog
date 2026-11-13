import { useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import {
  InvalidCredentialsError,
  NotFoundError,
  TooManyAttemptsError,
  ValidationError,
  demoLogin,
  login,
} from '../api/index.ts'
import { EmailField, FormAlert, FormNotice, PasswordField, SubmitButton } from '../auth/AuthFields.tsx'
import {
  ACCOUNT_CREATED_MESSAGE,
  ACCOUNT_DELETED_MESSAGE,
  DEMO_UNAVAILABLE_MESSAGE,
  OPENING_DEMO_LABEL,
  TRY_DEMO_LABEL,
  WAKING_UP_MESSAGE,
  WRONG_CREDENTIALS_MESSAGE,
  tooManyAttemptsMessage,
  unexpectedErrorMessage,
  validationMessages,
} from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { PASSWORD_MISSING, emailProblem } from '../auth/validation.ts'
import { REGISTER_PATH, cameFromAccountDeletion, cameFromRegistration, wantedPage } from '../auth/wantedPage.ts'
import { Button } from '../components/Button.tsx'
import { LoginIllustration } from '../components/Illustrations.tsx'
import Message from '../components/Message.tsx'
import '../auth/AuthForm.css'

type Field = 'email' | 'password'

/** The message below "Try the demo" for a failed demo login. The server's text is never shown. */
function demoErrorMessage(error: unknown): string {
  // `not_found`: the demo is turned off or not seeded.
  if (error instanceof NotFoundError) {
    return DEMO_UNAVAILABLE_MESSAGE
  }
  // FR-A4: too many demo logins from this visitor.
  if (error instanceof TooManyAttemptsError) {
    return tooManyAttemptsMessage(error.retryAfterSeconds)
  }
  return unexpectedErrorMessage(error)
}

/** The information message above the form for the state the page was opened with, or null. */
function noticeFor(state: unknown): string | null {
  if (cameFromRegistration(state)) {
    return ACCOUNT_CREATED_MESSAGE
  }
  return cameFromAccountDeletion(state) ? ACCOUNT_DELETED_MESSAGE : null
}

// FR-A2: log in. Login checks no password rule; it only needs both fields filled in.
// FR-X1: "Try the demo" below the form logs in to the shared demo account without the
// fields. The two requests block each other, and each clears the other's message.
export default function LoginPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [checked, setChecked] = useState<Record<Field, boolean>>({ email: false, password: false })
  const [serverMessages, setServerMessages] = useState<Record<Field, string[]>>({ email: [], password: [] })
  const [formError, setFormError] = useState<string | null>(null)
  // "Account created" after a failed automatic login, "account deleted" after FR-D2.
  const [notice, setNotice] = useState<string | null>(() => noticeFor(location.state))
  const [pending, setPending] = useState(false)
  const wakingUp = useWakingUpHint(pending)
  const [demoPending, setDemoPending] = useState(false)
  const [demoError, setDemoError] = useState<string | null>(null)
  const demoWakingUp = useWakingUpHint(demoPending)
  // Answers a second press before React renders again, so it sends nothing.
  const requestRunning = useRef(false)
  // True from a press on "Try the demo" until its request fails. Leaving a field then
  // checks nothing: a second press lands on the busy (disabled) button, which runs no
  // handler, so the browser moves focus to the page and the field is blurred (QA on #35).
  const demoRunning = useRef(false)

  const emailError = emailProblem(email)
  const passwordError = password === '' ? PASSWORD_MISSING : null
  const emailMessages = [...(checked.email && emailError !== null ? [emailError] : []), ...serverMessages.email]
  const passwordMessages = [
    ...(checked.password && passwordError !== null ? [passwordError] : []),
    ...serverMessages.password,
  ]

  function change(field: Field, value: string) {
    if (field === 'email') {
      setEmail(value)
    } else {
      setPassword(value)
    }
    setServerMessages((current) => ({ ...current, [field]: [] }))
  }

  function check(field: Field) {
    if (demoRunning.current) {
      return
    }
    setChecked((current) => ({ ...current, [field]: true }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (requestRunning.current) {
      return
    }
    setChecked({ email: true, password: true })
    if (emailError !== null) {
      emailRef.current?.focus()
      return
    }
    if (passwordError !== null) {
      passwordRef.current?.focus()
      return
    }

    setFormError(null)
    setServerMessages({ email: [], password: [] })
    setNotice(null)
    setDemoError(null)
    requestRunning.current = true
    setPending(true)
    try {
      await login({ email, password })
    } catch (error) {
      requestRunning.current = false
      setPending(false)
      if (error instanceof InvalidCredentialsError) {
        setFormError(WRONG_CREDENTIALS_MESSAGE)
      } else if (error instanceof TooManyAttemptsError) {
        // FR-A4: too many failed logins for this email.
        setFormError(tooManyAttemptsMessage(error.retryAfterSeconds))
      } else if (error instanceof ValidationError) {
        showValidationError(error)
      } else {
        setFormError(unexpectedErrorMessage(error))
      }
      return
    }
    await navigate(wantedPage(location.state), { replace: true })
  }

  // No field check: the demo needs no email or password, and anything typed stays.
  async function handleDemo() {
    if (requestRunning.current) {
      return
    }
    setNotice(null)
    setFormError(null)
    setDemoError(null)
    requestRunning.current = true
    demoRunning.current = true
    setDemoPending(true)
    try {
      // Stores the token with the demo flag (#25).
      await demoLogin()
    } catch (error) {
      requestRunning.current = false
      demoRunning.current = false
      setDemoPending(false)
      setDemoError(demoErrorMessage(error))
      return
    }
    await navigate(wantedPage(location.state), { replace: true })
  }

  function showValidationError(error: ValidationError) {
    const { email: emailReasons, password: passwordReasons, form } = validationMessages(error)
    setServerMessages({ email: emailReasons, password: passwordReasons })
    setFormError(form)
  }

  return (
    <section className="auth-page">
      <LoginIllustration />
      <h1>Log in</h1>
      <FormNotice message={notice} />
      <FormAlert message={formError} />
      <form className="form" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <EmailField
          id="login-email"
          value={email}
          onChange={(value) => change('email', value)}
          onBlur={() => check('email')}
          messages={emailMessages}
          inputRef={emailRef}
        />
        <PasswordField
          id="login-password"
          value={password}
          onChange={(value) => change('password', value)}
          onBlur={() => check('password')}
          messages={passwordMessages}
          inputRef={passwordRef}
          autoComplete="current-password"
        />
        <SubmitButton
          pending={pending}
          label="Log in"
          pendingLabel="Logging in…"
          wakingUp={wakingUp}
          disabled={demoPending}
        />
      </form>
      {/* Outside the form, so Enter in a field always submits the login form. */}
      <Button
        className="auth-page__demo"
        variant="secondary"
        type="button"
        busy={demoPending}
        busyLabel={OPENING_DEMO_LABEL}
        disabled={pending}
        // A mouse press or tap must not move focus: leaving a field would run its blur
        // check, and the field message it shows pushes this button down between press
        // and release, so the click is lost (QA on #35). Keyboard use is unaffected. The
        // busy button is disabled and runs no handler, so `demoRunning` covers later presses.
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => void handleDemo()}
      >
        {TRY_DEMO_LABEL}
      </Button>
      <div className="auth-page__demo-messages">
        <Message variant="error">{demoError}</Message>
        <Message variant="info">{demoWakingUp ? WAKING_UP_MESSAGE : null}</Message>
      </div>
      <p className="auth-page__switch">
        New to Winlog? <Link to={REGISTER_PATH}>Create an account</Link>
      </p>
    </section>
  )
}
