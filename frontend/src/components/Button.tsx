import type { ComponentProps, ReactNode } from 'react'
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
  /** While true, shows the spinner and `busyLabel`, and cannot be pressed. */
  busy?: boolean
  /** The label while busy, for example "Logging in…". */
  busyLabel?: ReactNode
}

/** A button in the primary or secondary style, with normal, disabled and busy states. */
export function Button({
  variant = 'primary',
  size = 'normal',
  busy = false,
  busyLabel,
  disabled = false,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={buttonClassName(variant, size, className)}
      disabled={disabled || busy}
      aria-busy={busy}
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
