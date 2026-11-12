import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/ and https://vitest.dev/config/
export default defineConfig({
  plugins: [react()],
  // Read VITE_ variables from the repository-root .env, next to the backend's settings.
  // Only VITE_-prefixed variables reach the browser bundle.
  envDir: '..',
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // A time zone ahead of UTC, so tests notice a local date worked out in UTC (#27: the
    // entry form pre-fills today's date in the user's own time zone). Node reads TZ when
    // the test process starts, so it is set here, not in a test.
    env: { TZ: 'Australia/Sydney' },
  },
})
