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

interface LeavePromptOptions {
  /**
   * Lets a navigation that stays on the same path through without asking, for example a
   * filter change on the review page, which only changes the query (#32). Off by default:
   * on the entry forms, "New entry" on /entries/new starts a new form, so it asks.
   */
  allowSamePath?: boolean
}

/**
 * Asks "Discard changes?" before leaving a page with unsaved changes: through any link,
 * Cancel, or the browser's back button. Closing or reloading the tab gets the browser's
 * own prompt. Logging out and the redirect after an expired login (both open the login
 * page) never ask.
 */
export function useLeavePrompt(dirty: boolean, { allowSamePath = false }: LeavePromptOptions = {}): LeavePrompt {
  const leavingRef = useRef(false)

  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      !leavingRef.current &&
      nextLocation.pathname !== LOGIN_PATH &&
      !(allowSamePath && nextLocation.pathname === currentLocation.pathname),
    [dirty, allowSamePath],
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
