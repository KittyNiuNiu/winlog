import { useEffect, useState } from 'react'
import { WAKING_UP_AFTER_MS } from './requestErrors.ts'

/** True once `pending` has been true for 10 seconds without a break. */
export function useWakingUpHint(pending: boolean): boolean {
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    if (!pending) {
      return undefined
    }
    const timer = window.setTimeout(() => setSlow(true), WAKING_UP_AFTER_MS)
    return () => {
      window.clearTimeout(timer)
      setSlow(false)
    }
  }, [pending])

  return pending && slow
}
