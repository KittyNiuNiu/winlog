import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { EmailAlreadyRegisteredError, ValidationError, login, register } from '../api/index.ts'
import { EmailField, FormAlert, PasswordField, SubmitButton } from '../auth/AuthFields.tsx'
import { unexpectedErrorMessage, validationMessages } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { PASSWORD_HINT, PASSWORD_MESSAGES, emailProblem, passwordProblems } from '../auth/validation.ts'
import { LOGIN_PATH, type LoginPageState } from '../auth/wantedPage.ts'
import { LoginIllustration } from '../components/Illustrations.tsx'
import '../auth/AuthForm.css'

type Field = 'email' | 'password'

// FR-A1: register with an email and a password, then log in with the same details. The
// form checks the password rule from #6 first; the backend stays the authority.
export default function RegisterPage() {
  const navigate = useNavigate()
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [checked, setChecked] = useState<Record<Field, boolean>>({ email: false, password: false })
  const [serverMessages, setServerMessages] = useState<Record<Field, string[]>>({ email: [], password: [] })
  const [emailTaken, setEmailTaken] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const wakingUp = useWakingUpHint(pending)

  const emailError = emailProblem(email)
  const passwordErrors = passwordProblems(password).map((problem) => PASSWORD_MESSAGES[problem])

  const emailMessages: ReactNode[] = [
    ...(checked.email && emailError !== null ? [emailError] : []),
    ...serverMessages.email,
  ]
  if (emailTaken) {
    emailMessages.push(
      <>
        Email already registered. <Link to={LOGIN_PATH}>Log in instead</Link>
      </>,
    )
  }
  const passwordMessages = [...(checked.password ? passwordErrors : []), ...serverMessages.password]

  function change(field: Field, value: string) {
    if (field === 'email') {
      setEmail(value)
      setEmailTaken(false)
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
    if (passwordErrors.length > 0) {
      passwordRef.current?.focus()
      return
    }

    setFormError(null)
    setServerMessages({ email: [], password: [] })
    setEmailTaken(false)
    setPending(true)
    try {
      await register({ email, password })
    } catch (error) {
      setPending(false)
      if (error instanceof EmailAlreadyRegisteredError) {
        setEmailTaken(true)
        emailRef.current?.focus()
      } else if (error instanceof ValidationError) {
        showValidationError(error)
      } else {
        setFormError(unexpectedErrorMessage(error))
      }
      return
    }

    // FR-A1: after registering, the user is logged in. Registration returns no token.
    try {
      await login({ email, password })
    } catch {
      const state: LoginPageState = { accountCreated: true }
      await navigate(LOGIN_PATH, { replace: true, state })
      return
    }
    await navigate('/', { replace: true })
  }

  function showValidationError(error: ValidationError) {
    const { email: emailReasons, password: passwordReasons, form } = validationMessages(error)
    setServerMessages({ email: emailReasons, password: passwordReasons })
    setFormError(form)
  }

  return (
    <section className="auth-page">
      <LoginIllustration />
      <h1>Create an account</h1>
      <FormAlert message={formError} />
      <form className="form" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <EmailField
          id="register-email"
          value={email}
          onChange={(value) => change('email', value)}
          onBlur={() => check('email')}
          messages={emailMessages}
          inputRef={emailRef}
        />
        <PasswordField
          id="register-password"
          value={password}
          onChange={(value) => change('password', value)}
          onBlur={() => check('password')}
          messages={passwordMessages}
          inputRef={passwordRef}
          autoComplete="new-password"
          hint={PASSWORD_HINT}
        />
        <SubmitButton pending={pending} label="Create account" pendingLabel="Creating account…" wakingUp={wakingUp} />
      </form>
      <p className="auth-page__switch">
        Already have an account? <Link to={LOGIN_PATH}>Log in</Link>
      </p>
    </section>
  )
}
