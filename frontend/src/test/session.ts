import { clearSession, saveSession } from '../api/session.ts'

export const TEST_TOKEN = 'test-token'

/** Stores a valid session, as after a login. */
export function storeTestSession(): void {
  saveSession({ token: TEST_TOKEN, expiresAt: '2099-01-01T00:00:00Z', demo: false })
}

/** Removes the stored session, in memory and in localStorage. */
export function removeTestSession(): void {
  clearSession()
  localStorage.clear()
}
