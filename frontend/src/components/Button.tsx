import type { ComponentProps, MouseEvent, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router'
import './Button.css'

type Variant = 'primary' | 'secondary'
type Size = 'normal' | 'large'

interface ButtonStyleProps {
  /** Primary: the one filled plum action on a screen. Secondary: everything else. */
  variant?: Variant
  /** Large is the phone's "Save entry" (54px tall). */
  size?: Size
}

function buttonClassName(variant: Variant, size: Size, className: string | undefined): string {
  return ['button', `button--${variant}`, size === 'large' && 'button--large', className].filter(Boolean).join(' ')
}

interface ButtonProps extends ButtonStyleProps, ComponentProps<'button'> {
  /**
   * While true, shows the spinner and `busyLabel`, and cannot be pressed. A busy button stays
   * focusable (`aria-disabled`, not native `disabled`), so keyboard focus stays on it (#84).
   */
  busy?: boolean
  /** The label while busy, for example "Logging in…". */
  busyLabel?: ReactNode
}

/**
 * A button in the primary or secondary style, with normal, disabled and busy states.
 *
 * `disabled` alone is the native attribute. `busy` wins over it: the button keeps focus, is
 * announced as unavailable through `aria-disabled`, and ignores presses itself, because
 * `aria-disabled` does not stop the browser from running the click or submitting the form.
 * Enter and Space on a button reach it as a click, so ignoring the click covers them too.
 */
export function Button({
  variant = 'primary',
  size = 'normal',
  busy = false,
  busyLabel,
  disabled = false,
  className,
  type = 'button',
  onClick,
  children,
  ...rest
}: ButtonProps) {
  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    if (busy) {
      // Stops a busy submit button from submitting its form, as native `disabled` did.
      event.preventDefault()
      return
    }
    onClick?.(event)
  }

  return (
    <button
      {...rest}
      type={type}
      className={buttonClassName(variant, size, className)}
      disabled={busy ? undefined : disabled}
      aria-disabled={busy ? true : rest['aria-disabled']}
      aria-busy={busy}
      onClick={handleClick}
    >
      {busy && <span className="spinner" aria-hidden="true" />}
      {busy && busyLabel !== undefined ? busyLabel : children}
    </button>
  )
}

type ButtonLinkProps = ButtonStyleProps & LinkProps

/** A link that looks like a button, for example "New entry" in the sidebar. */
export function ButtonLink({ variant = 'secondary', size = 'normal', className, ...rest }: ButtonLinkProps) {
  return <Link {...rest} className={buttonClassName(variant, size, className)} />
}
