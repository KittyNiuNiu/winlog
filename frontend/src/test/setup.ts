import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { installDialogStub } from './dialog.ts'
import { installMatchMedia, resetViewport } from './viewport.ts'

installMatchMedia()
installDialogStub()

// Vitest globals are off, so React Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup()
  resetViewport()
})
