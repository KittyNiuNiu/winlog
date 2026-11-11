import { act } from '@testing-library/react'
import { LAPTOP_QUERY } from '../components/useMediaQuery.ts'

// jsdom has no layout and no window.matchMedia. This stub answers the laptop media query
// (min-width: 48rem) for the width a test sets; every other query does not match.

type Viewport = 'phone' | 'laptop'

let viewport: Viewport = 'phone'
const listeners = new Set<() => void>()

function matches(query: string): boolean {
  return viewport === 'laptop' && query === LAPTOP_QUERY
}

/** Installs the stub (only where there is a window). Tests start at phone width. */
export function installMatchMedia(): void {
  if (typeof window === 'undefined') {
    return
  }
  window.matchMedia = (query: string) =>
    ({
      media: query,
      get matches() {
        return matches(query)
      },
      onchange: null,
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
      addListener: (listener: () => void) => listeners.add(listener),
      removeListener: (listener: () => void) => listeners.delete(listener),
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}

/** Sets the width the app is shown at, and tells the app when it changes. */
export function setViewport(next: Viewport): void {
  if (next === viewport) {
    return
  }
  viewport = next
  act(() => {
    for (const listener of listeners) {
      listener()
    }
  })
}

/** Back to phone width, without notifying (between tests). */
export function resetViewport(): void {
  viewport = 'phone'
  listeners.clear()
}
