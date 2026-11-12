import { useCallback, useEffect, useRef, useState } from 'react'

/** How long the saved message stays after it was last shown (design note on #75). */
export const SAVED_MESSAGE_MS = 5_000
/** It fades out during its last 300ms (no fade with reduced motion). */
export const SAVED_MESSAGE_FADE_MS = 300

export type SavedMessagePhase = 'hidden' | 'shown' | 'leaving'

export interface SavedMessageState {
  phase: SavedMessagePhase
  /** How often it was shown. Each new value makes screen readers announce it again. */
  count: number
}

/**
 * The state of a saved message. `show()` shows it, or, while it is visible, keeps it and
 * starts its time again; there is never a second message.
 */
export function useSavedMessage(): SavedMessageState & { show: () => void } {
  const [state, setState] = useState<SavedMessageState>({ phase: 'hidden', count: 0 })
  const timers = useRef<number[]>([])

  const clearTimers = useCallback(() => {
    for (const timer of timers.current) {
      window.clearTimeout(timer)
    }
    timers.current = []
  }, [])

  useEffect(() => clearTimers, [clearTimers])

  const show = useCallback(() => {
    clearTimers()
    setState((current) => ({ phase: 'shown', count: current.count + 1 }))
    timers.current = [
      window.setTimeout(
        () => setState((current) => ({ ...current, phase: 'leaving' })),
        SAVED_MESSAGE_MS - SAVED_MESSAGE_FADE_MS,
      ),
      window.setTimeout(() => setState((current) => ({ ...current, phase: 'hidden' })), SAVED_MESSAGE_MS),
    ]
  }, [clearTimers])

  return { ...state, show }
}
