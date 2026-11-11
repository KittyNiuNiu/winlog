import { useState, type ReactNode, type Ref } from 'react'
import { WAKING_UP_MESSAGE } from './requestErrors.ts'

// Form fields shared by the login and registration pages. Every field has a visible
// label, and its messages sit under it in a live region (role="alert") that is always in
// the page, so screen readers announce each new message.

interface FieldMessagesProps {
  id: string
  messages: ReactNode[]
}

function FieldMessages({ id, messages }: FieldMessagesProps) {
  return (
    <div className="field__messages" id={id} role="alert">
      {messages.map((message, index) => (
        <p className="field__message" key={index}>
          {message}
        </p>
      ))}
    </div>
  )
}

function describedBy(...ids: (string | false | undefined)[]): string | undefined {
  const present = ids.filter((id): id is string => typeof id === 'string' && id !== '')
  return present.length > 0 ? present.join(' ') : undefined
}

interface InputFieldProps {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur: () => void
  messages: ReactNode[]
  inputRef?: Ref<HTMLInputElement>
}

export function EmailField({ id, value, onChange, onBlur, messages, inputRef }: InputFieldProps) {
  const messagesId = `${id}-messages`
  const invalid = messages.length > 0
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        Email
      </label>
      <input
        className="field__input"
        id={id}
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
        aria-invalid={invalid}
        aria-describedby={describedBy(invalid && messagesId)}
      />
      <FieldMessages id={messagesId} messages={messages} />
    </div>
  )
}

interface PasswordFieldProps extends InputFieldProps {
  autoComplete: 'new-password' | 'current-password'
  hint?: string
}

export function PasswordField({ id, value, onChange, onBlur, messages, inputRef, autoComplete, hint }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)
  const messagesId = `${id}-messages`
  const hintId = `${id}-hint`
  const invalid = messages.length > 0
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        Password
      </label>
      {hint !== undefined && (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      )}
      <div className="password-input">
        <input
          className="field__input password-input__input"
          id={id}
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
          aria-invalid={invalid}
          aria-describedby={describedBy(hint !== undefined && hintId, invalid && messagesId)}
        />
        <button
          className="password-input__toggle"
          type="button"
          aria-controls={id}
          aria-label={visible ? 'Hide password' : 'Show password'}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? 'Hide' : 'Show'}
        </button>
      </div>
      <FieldMessages id={messagesId} messages={messages} />
    </div>
  )
}

interface FormAlertProps {
  message: string | null
}

/** A message about the whole form, above its fields. Announced when it appears. */
export function FormAlert({ message }: FormAlertProps) {
  return (
    <div className="form__alert" role="alert">
      {message !== null && <p className="form__alert-text">{message}</p>}
    </div>
  )
}

interface SubmitButtonProps {
  pending: boolean
  label: string
  pendingLabel: string
  wakingUp: boolean
}

/** The submit button: disabled with a progress label while the request runs. */
export function SubmitButton({ pending, label, pendingLabel, wakingUp }: SubmitButtonProps) {
  return (
    <>
      <button className="button form__submit" type="submit" disabled={pending} aria-busy={pending}>
        {pending && <span className="spinner" aria-hidden="true" />}
        {pending ? pendingLabel : label}
      </button>
      <div className="form__status" role="status">
        {wakingUp && <p>{WAKING_UP_MESSAGE}</p>}
      </div>
    </>
  )
}
