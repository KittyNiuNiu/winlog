import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'
import { installDialogStub } from './dialog.ts'
import { blockNetwork } from './network.ts'
import { installMatchMedia, resetViewport } from './viewport.ts'

installMatchMedia()
installDialogStub()

// No test sends a request over the network: unmocked requests fail like an unreachable
// server (#73). Set before every test, so a test that replaced fetch cannot leak it.
beforeEach(() => {
  blockNetwork()
})

// Vitest globals are off, so React Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup()
  resetViewport()
})
