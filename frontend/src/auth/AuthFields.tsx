import { useState, type ReactNode, type Ref } from 'react'
import { Button } from '../components/Button.tsx'
import Message from '../components/Message.tsx'
import { TextField } from '../components/TextField.tsx'
import { WAKING_UP_MESSAGE } from './requestErrors.ts'

// Form fields shared by the login and registration pages, built from the shared
// components. Every field has a visible label, and its messages sit under it in a live
// region (role="alert") that is always in the page, so screen readers announce each new
// message.

interface InputFieldProps {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  messages: ReactNode[]
  inputRef?: Ref<HTMLInputElement>
}

export function EmailField({ id, value, onChange, onBlur, messages, inputRef }: InputFieldProps) {
  return (
    <TextField
      id={id}
      label="Email"
      messages={messages}
      ref={inputRef}
      name="email"
      type="email"
      inputMode="email"
      autoComplete="email"
      autoCapitalize="none"
      spellCheck={false}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onBlur}
    />
  )
}

interface PasswordFieldProps extends InputFieldProps {
  autoComplete: 'new-password' | 'current-password'
  hint?: string
  /** The visible label. Login and registration use the default, "Password". */
  label?: string
  /** True while a request runs: the value cannot change, the Show/Hide toggle still works. */
  readOnly?: boolean
}

/**
 * A password field with its Show/Hide toggle. The toggle state lives here, so a caller that
 * must hide the password again (for example after Cancel) remounts the field.
 */
export function PasswordField({
  id,
  value,
  onChange,
  onBlur,
  messages,
  inputRef,
  autoComplete,
  hint,
  label = 'Password',
  readOnly,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)
  return (
    <TextField
      id={id}
      label={label}
      hint={hint}
      readOnly={readOnly}
      messages={messages}
      ref={inputRef}
      name="password"
      type={visible ? 'text' : 'password'}
      autoComplete={autoComplete}
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onBlur}
      after={
        <Button
          className="password-toggle"
          variant="secondary"
          aria-controls={id}
          aria-label={visible ? 'Hide password' : 'Show password'}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? 'Hide' : 'Show'}
        </Button>
      }
    />
  )
}

interface FormAlertProps {
  message: string | null
}

/** A message about the whole form, above its fields. Announced when it appears. */
export function FormAlert({ message }: FormAlertProps) {
  return (
    <Message variant="error" className="form__alert">
      {message}
    </Message>
  )
}

interface FormNoticeProps {
  message: string | null
}

/** Information about the whole form, above its fields, for example "Account created." */
export function FormNotice({ message }: FormNoticeProps) {
  return (
    <Message variant="info" className="form__notice">
      {message}
    </Message>
  )
}

interface SubmitButtonProps {
  pending: boolean
  label: string
  pendingLabel: string
  wakingUp: boolean
  /** True while another request on the page runs, for example the demo login. */
  disabled?: boolean
}

/** The submit button: busy with a progress label while the request runs. */
export function SubmitButton({ pending, label, pendingLabel, wakingUp, disabled }: SubmitButtonProps) {
  return (
    <>
      <Button className="form__submit" type="submit" busy={pending} busyLabel={pendingLabel} disabled={disabled}>
        {label}
      </Button>
      <Message variant="info" className="form__status">
        {wakingUp ? WAKING_UP_MESSAGE : null}
      </Message>
    </>
  )
}
