import { useCallback, useSyncExternalStore } from 'react'

/** The laptop layout starts at 48rem, as in the CSS. */
export const LAPTOP_QUERY = '(min-width: 48rem)'

/** Whether a media query matches now. Updates when it starts or stops matching. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window.matchMedia !== 'function') {
        return () => {}
      }
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => typeof window.matchMedia === 'function' && window.matchMedia(query).matches)
}
