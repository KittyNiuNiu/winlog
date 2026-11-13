import { defineConfig, devices } from '@playwright/test'

// End-to-end smoke test (#37): the main user flow in Chromium at 1280×800 (#36's "laptop"),
// against a running Winlog with the real backend, its database and the mock AI provider.
// It starts nothing itself (no webServer): start the system first, see AGENTS.md. The base
// URL comes from E2E_BASE_URL, by default the frontend container's port. Run with
// `npm run test:e2e`.

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  // Traces and screenshots of failed tests. CI uploads this folder when the job fails.
  outputDir: './e2e-results',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  // The whole flow is one test of about ten steps against a real backend.
  timeout: 120_000,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8080',
    browserName: 'chromium',
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    locale: 'en-US',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
})
