// The stored login: the token, when it expires, and whether it is a demo session (#21).
// It lives in localStorage so it survives a reload, and stays until logout, account
// deletion or expiry (#25, token decision in #2). Every storage access is wrapped: when
// storage is blocked or unavailable, the session is kept in memory only, so the app works
// until the next reload and the user then logs in again.

const STORAGE_KEY = 'winlog.session'

export interface Session {
  /** Sent as `Authorization: Bearer <token>`. */
  readonly token: string
  /** When the token stops working (ISO 8601 date-time from the server). */
  readonly expiresAt: string
  /** True for a session of the shared demo account. */
  readonly demo: boolean
}

// undefined: not read from storage yet. null: no session.
let current: Session | null | undefined

function storage(): Storage | null {
  try {
    return window.localStorage ?? null
  } catch {
    return null
  }
}

function parse(raw: string | null): Session | null {
  if (raw === null) {
    return null
  }
  try {
    const value: unknown = JSON.parse(raw)
    if (typeof value !== 'object' || value === null) {
      return null
    }
    const { token, expiresAt, demo } = value as Record<string, unknown>
    if (typeof token !== 'string' || token === '' || typeof expiresAt !== 'string' || typeof demo !== 'boolean') {
      return null
    }
    return { token, expiresAt, demo }
  } catch {
    return null
  }
}

function readStored(): Session | null {
  try {
    const session = parse(storage()?.getItem(STORAGE_KEY) ?? null)
    if (session === null) {
      // Drop anything unreadable, so it is not read again.
      storage()?.removeItem(STORAGE_KEY)
    }
    return session
  } catch {
    return null
  }
}

function isExpired(session: Session): boolean {
  const expiresAt = Date.parse(session.expiresAt)
  return Number.isNaN(expiresAt) || expiresAt <= Date.now()
}

/** The current session, or null when the user is not logged in or the token has expired. */
export function getSession(): Session | null {
  if (current === undefined) {
    current = readStored()
  }
  if (current !== null && isExpired(current)) {
    clearSession()
  }
  return current
}

/** Stores a new session, replacing any earlier one. */
export function saveSession(session: Session): void {
  current = session
  try {
    storage()?.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Storage is blocked or full: the session stays in memory until the next reload.
  }
}

/** Removes the stored token and demo flag. */
export function clearSession(): void {
  current = null
  try {
    storage()?.removeItem(STORAGE_KEY)
  } catch {
    // Storage is blocked: nothing was stored there.
  }
}
