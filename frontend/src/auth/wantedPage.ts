// What the login page receives in the history state: the page a logged-out visitor wanted,
// and whether they come from a registration whose automatic login failed.
import type { Location } from 'react-router'

export interface LoginPageState {
  /** Path, query and hash of the page the visitor wanted, for example `/review?x=1`. */
  from?: string
  /** True after a registration whose automatic login failed. */
  accountCreated?: boolean
}

export const LOGIN_PATH = '/login'
export const REGISTER_PATH = '/register'

/** True for the pages only logged-out visitors see. */
export function isGuestPath(pathname: string): boolean {
  return pathname === LOGIN_PATH || pathname === REGISTER_PATH
}

/** The login page state that remembers `location`, or undefined for the guest pages. */
export function rememberWantedPage(location: Pick<Location, 'pathname' | 'search' | 'hash'>): LoginPageState | undefined {
  if (isGuestPath(location.pathname)) {
    return undefined
  }
  return { from: `${location.pathname}${location.search}${location.hash}` }
}

/**
 * Where to go after logging in: the remembered page if it is a path inside the app, else
 * `/`. The state comes from the browser history, so anything else is ignored.
 */
export function wantedPage(state: unknown): string {
  if (typeof state !== 'object' || state === null) {
    return '/'
  }
  const { from } = state as Record<string, unknown>
  // A path inside this app: one leading slash, not `//host` or `/\host`.
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//') || from.startsWith('/\\')) {
    return '/'
  }
  const pathname = from.split(/[?#]/, 1)[0]
  return isGuestPath(pathname) ? '/' : from
}

/** True when the login page was opened after a registration whose automatic login failed. */
export function cameFromRegistration(state: unknown): boolean {
  return typeof state === 'object' && state !== null && (state as Record<string, unknown>).accountCreated === true
}
