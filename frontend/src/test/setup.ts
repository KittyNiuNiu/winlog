import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { installMatchMedia, resetViewport } from './viewport.ts'

installMatchMedia()

// Vitest globals are off, so React Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup()
  resetViewport()
})
