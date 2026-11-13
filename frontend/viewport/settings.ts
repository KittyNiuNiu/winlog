// Shared settings of the viewport tests (#36), used by playwright.config.ts and the tests.

/** The port `vite preview` serves the test build on. */
export const PREVIEW_PORT = 4319

/**
 * The API base URL the test build is made with. Nothing listens there: the tests answer
 * every request to it (mockApi.ts), and any other request fails the test.
 */
export const API_BASE_URL = 'http://api.winlog.test'

/** The fixed "now" of every test: a Friday, 13 November 2026, 10:00 in London. */
export const NOW = new Date('2026-11-13T10:00:00Z')

/** Today's date at NOW, in the browser's time zone (Europe/London). */
export const TODAY = '2026-11-13'

/** Where the screenshots go. CI uploads this folder. */
export const SCREENSHOT_DIR = 'viewport-screenshots'

/** The browser's time zone in every test. */
export const TIME_ZONE = 'Europe/London'
