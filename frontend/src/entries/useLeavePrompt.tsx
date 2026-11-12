import { useCallback, useRef, type ReactNode } from 'react'
import { useBeforeUnload, useBlocker, type BlockerFunction } from 'react-router'
import { LOGIN_PATH } from '../auth/wantedPage.ts'
import DiscardDialog from './DiscardDialog.tsx'

interface LeavePrompt {
  /** The "Discard changes?" dialog, to render on the page. */
  dialog: ReactNode
  /** Lets the next navigation leave without asking, for example right after saving. */
  allowLeaving: () => void
}

/**
 * Asks "Discard changes?" before leaving a page with unsaved changes: through any link,
 * Cancel, or the browser's back button. Closing or reloading the tab gets the browser's
 * own prompt. Logging out and the redirect after an expired login (both open the login
 * page) never ask.
 */
export function useLeavePrompt(dirty: boolean): LeavePrompt {
  const leavingRef = useRef(false)

  const shouldBlock = useCallback<BlockerFunction>(
    ({ nextLocation }) => dirty && !leavingRef.current && nextLocation.pathname !== LOGIN_PATH,
    [dirty],
  )
  const blocker = useBlocker(shouldBlock)

  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (dirty && !leavingRef.current) {
          event.preventDefault()
          // Older browsers show their prompt only when returnValue is set.
          event.returnValue = ''
        }
      },
      [dirty],
    ),
  )

  const allowLeaving = useCallback(() => {
    leavingRef.current = true
  }, [])

  const dialog = (
    <DiscardDialog
      open={blocker.state === 'blocked'}
      onKeepEditing={() => blocker.reset?.()}
      onDiscard={() => blocker.proceed?.()}
    />
  )

  return { dialog, allowLeaving }
}
