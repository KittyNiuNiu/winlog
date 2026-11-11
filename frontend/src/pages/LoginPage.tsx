import { useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { InvalidCredentialsError, ValidationError, login } from '../api/index.ts'
import { EmailField, FormAlert, PasswordField, SubmitButton } from '../auth/AuthFields.tsx'
import {
  ACCOUNT_CREATED_MESSAGE,
  WRONG_CREDENTIALS_MESSAGE,
  unexpectedErrorMessage,
  validationMessages,
} from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { PASSWORD_MISSING, emailProblem } from '../auth/validation.ts'
import { REGISTER_PATH, cameFromRegistration, wantedPage } from '../auth/wantedPage.ts'
import '../auth/AuthForm.css'

type Field = 'email' | 'password'

// FR-A2: log in. Login checks no password rule; it only needs both fields filled in.
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
  const [showAccountCreated, setShowAccountCreated] = useState(() => cameFromRegistration(location.state))
  const [pending, setPending] = useState(false)
  const wakingUp = useWakingUpHint(pending)

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
    setChecked((current) => ({ ...current, [field]: true }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) {
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
    setShowAccountCreated(false)
    setPending(true)
    try {
      await login({ email, password })
    } catch (error) {
      setPending(false)
      if (error instanceof InvalidCredentialsError) {
        setFormError(WRONG_CREDENTIALS_MESSAGE)
      } else if (error instanceof ValidationError) {
        showValidationError(error)
      } else {
        setFormError(unexpectedErrorMessage(error))
      }
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
      <h1>Log in</h1>
      {showAccountCreated && (
        <p className="form__notice" role="status">
          {ACCOUNT_CREATED_MESSAGE}
        </p>
      )}
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
        <SubmitButton pending={pending} label="Log in" pendingLabel="Logging in…" wakingUp={wakingUp} />
      </form>
      <p className="auth-page__switch">
        New to Winlog? <Link to={REGISTER_PATH}>Create an account</Link>
      </p>
    </section>
  )
}
