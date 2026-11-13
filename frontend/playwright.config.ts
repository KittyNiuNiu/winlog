import { defineConfig, devices } from '@playwright/test'
import { API_BASE_URL, PREVIEW_PORT, TIME_ZONE } from './viewport/settings.ts'

// Viewport tests (#36): every screen and state at 360×640 ("phone") and 1280×800
// ("laptop") in Chromium, against the production build served by `vite preview`. Every API
// call is answered by the tests (viewport/mockApi.ts), so no backend is needed. The
// screenshots go to viewport-screenshots/ for people to look at; they are not compared.
// Run with `npm run test:viewport`.

export default defineConfig({
  testDir: './viewport',
  testMatch: '**/*.spec.ts',
  outputDir: './viewport-results',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: `http://localhost:${PREVIEW_PORT}`,
    browserName: 'chromium',
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: TIME_ZONE,
    // No traces or videos: the screenshots are the record.
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'phone',
      use: { ...devices['Desktop Chrome'], viewport: { width: 360, height: 640 }, deviceScaleFactor: 1 },
    },
    {
      name: 'laptop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
    },
  ],
  webServer: {
    // The same build as `npm run build`, with a fixed API base URL the tests intercept, in
    // its own folder so it never replaces dist/. Variables set here win over ../.env.
    command: `npm run build -- --outDir viewport-dist --emptyOutDir && npx vite preview --outDir viewport-dist --port ${PREVIEW_PORT} --strictPort`,
    env: { VITE_API_BASE_URL: API_BASE_URL },
    url: `http://localhost:${PREVIEW_PORT}`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
