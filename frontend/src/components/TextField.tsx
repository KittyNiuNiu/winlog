import type { ComponentProps, ReactNode } from 'react'
import { characterCounter, type CharacterCounter } from './inputLimits.ts'
import './TextField.css'

// Text field and text area (DESIGN.md → Inputs / Fields): a visible label above, an
// optional hint, and messages below. The messages sit in a live region (role="alert")
// that is always in the page, so screen readers announce each new message. Hint and
// messages are linked to the control with aria-describedby; with messages, the control
// is aria-invalid. A caller can link further elements (`describedBy`) and set the error
// state (`invalid`) for a hint or message that sits outside the field (#31).
//
// A text area with a character limit (`maxCharacters`, #43) shows a counter between the
// control and the messages from 80% of the limit. The counter is not a live region, so
// typing is never announced; it is linked with aria-describedby only while it shows. Over
// the limit it turns to the error colour and the field is aria-invalid. Typing and pasting
// past the limit are never blocked or cut (no `maxlength`, which counts UTF-16 units).

interface FieldProps {
  /** The control's id. The hint gets `<id>-hint`, the messages `<id>-messages`. */
  id: string
  label: string
  hint?: string
  /** Messages that say what to fix. Any message puts the field in its error state. */
  messages?: ReactNode[]
  /**
   * Ids of other elements that describe the control, for example a hint under the field
   * or a message shared by two fields. Linked after the hint and the messages.
   */
  describedBy?: string
  /** Puts the field in its error state for a message outside it. */
  invalid?: boolean
}

function describedBy(...ids: (string | false | undefined)[]): string | undefined {
  const present = ids.filter((id): id is string => typeof id === 'string' && id !== '')
  return present.length > 0 ? present.join(' ') : undefined
}

interface FieldFrameProps extends FieldProps {
  children: ReactNode
  counter?: CharacterCounter | null
}

function FieldFrame({ id, label, hint, messages = [], counter = null, children }: FieldFrameProps) {
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
      {counter !== null && (
        <p
          className={counter.over ? 'field__counter field__counter--over' : 'field__counter'}
          id={`${id}-counter`}
        >
          <span aria-hidden="true">{counter.visible}</span>
          <span className="visually-hidden">{counter.spoken}</span>
        </p>
      )}
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

function controlA11y(
  { id, hint, messages = [], describedBy: others, invalid: outsideError = false }: FieldProps,
  counter: CharacterCounter | null = null,
) {
  const hasMessages = messages.length > 0
  return {
    'aria-invalid': hasMessages || outsideError || counter?.over === true,
    // In the visual order: hint, counter, messages.
    'aria-describedby': describedBy(
      hint !== undefined && `${id}-hint`,
      counter !== null && `${id}-counter`,
      hasMessages && `${id}-messages`,
      others,
    ),
  }
}

type TextFieldProps = FieldProps &
  Omit<ComponentProps<'input'>, 'id' | 'aria-invalid' | 'aria-describedby'> & {
    /** Shown to the right of the input, for example the password's Show button. */
    after?: ReactNode
  }

/** A one-line field for text, email, password or date input. */
export function TextField({
  id,
  label,
  hint,
  messages,
  describedBy,
  invalid,
  after,
  className,
  ...inputProps
}: TextFieldProps) {
  return (
    <FieldFrame id={id} label={label} hint={hint} messages={messages}>
      <input
        {...inputProps}
        className={['field__input', className].filter(Boolean).join(' ')}
        id={id}
        {...controlA11y({ id, label, hint, messages, describedBy, invalid })}
      />
      {after}
    </FieldFrame>
  )
}

type TextAreaProps = FieldProps &
  Omit<ComponentProps<'textarea'>, 'id' | 'aria-invalid' | 'aria-describedby' | 'maxLength'> & {
    /** The field's character limit (#43): shows the counter from 80% of it. Needs a string `value`. */
    maxCharacters?: number
  }

/** A text area that grows with the user: at least 120px tall, resizable vertically. */
export function TextArea({
  id,
  label,
  hint,
  messages,
  describedBy,
  invalid,
  maxCharacters,
  className,
  ...textareaProps
}: TextAreaProps) {
  const { value } = textareaProps
  const counter =
    maxCharacters === undefined || typeof value !== 'string' ? null : characterCounter(value, maxCharacters)
  return (
    <FieldFrame id={id} label={label} hint={hint} messages={messages} counter={counter}>
      <textarea
        {...textareaProps}
        className={['field__input', 'field__input--area', className].filter(Boolean).join(' ')}
        id={id}
        {...controlA11y({ id, label, hint, messages, describedBy, invalid }, counter)}
      />
    </FieldFrame>
  )
}
