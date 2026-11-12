import type { ComponentProps, ReactNode } from 'react'
import './TextField.css'

// Text field and text area (DESIGN.md → Inputs / Fields): a visible label above, an
// optional hint, and messages below. The messages sit in a live region (role="alert")
// that is always in the page, so screen readers announce each new message. Hint and
// messages are linked to the control with aria-describedby; with messages, the control
// is aria-invalid.

interface FieldProps {
  /** The control's id. The hint gets `<id>-hint`, the messages `<id>-messages`. */
  id: string
  label: string
  hint?: string
  /** Messages that say what to fix. Any message puts the field in its error state. */
  messages?: ReactNode[]
}

function describedBy(...ids: (string | false | undefined)[]): string | undefined {
  const present = ids.filter((id): id is string => typeof id === 'string' && id !== '')
  return present.length > 0 ? present.join(' ') : undefined
}

interface FieldFrameProps extends FieldProps {
  children: ReactNode
}

function FieldFrame({ id, label, hint, messages = [], children }: FieldFrameProps) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {hint !== undefined && (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      <div className="field__control">{children}</div>
      <div className="field__messages" id={`${id}-messages`} role="alert">
        {messages.map((message, index) => (
          <p className="field__message" key={index}>
            {message}
          </p>
        ))}
      </div>
    </div>
  )
}

function controlA11y({ id, hint, messages = [] }: FieldProps) {
  const invalid = messages.length > 0
  return {
    'aria-invalid': invalid,
    'aria-describedby': describedBy(hint !== undefined && `${id}-hint`, invalid && `${id}-messages`),
  }
}

type TextFieldProps = FieldProps &
  Omit<ComponentProps<'input'>, 'id' | 'aria-invalid' | 'aria-describedby'> & {
    /** Shown to the right of the input, for example the password's Show button. */
    after?: ReactNode
  }

/** A one-line field for text, email, password or date input. */
export function TextField({ id, label, hint, messages, after, className, ...inputProps }: TextFieldProps) {
  return (
    <FieldFrame id={id} label={label} hint={hint} messages={messages}>
      <input
        {...inputProps}
        className={['field__input', className].filter(Boolean).join(' ')}
        id={id}
        {...controlA11y({ id, label, hint, messages })}
      />
      {after}
    </FieldFrame>
  )
}

type TextAreaProps = FieldProps & Omit<ComponentProps<'textarea'>, 'id' | 'aria-invalid' | 'aria-describedby'>

/** A text area that grows with the user: at least 120px tall, resizable vertically. */
export function TextArea({ id, label, hint, messages, className, ...textareaProps }: TextAreaProps) {
  return (
    <FieldFrame id={id} label={label} hint={hint} messages={messages}>
      <textarea
        {...textareaProps}
        className={['field__input', 'field__input--area', className].filter(Boolean).join(' ')}
        id={id}
        {...controlA11y({ id, label, hint, messages })}
      />
    </FieldFrame>
  )
}
