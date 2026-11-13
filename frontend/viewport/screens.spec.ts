import { expect, test, type Locator, type Page } from '@playwright/test'
import { EDIT_ENTRY, ENTRIES_WITHOUT_NUDGE, ENTRIES_WITH_NUDGE, LONG_SUMMARY, MISSING_ID, SUMMARIES } from './data.ts'
import {
  checkScreen,
  expectOnlyMockedRequests,
  prepare,
  screenshot,
  settle,
  sizeOf,
  type SessionKind,
  type Size,
} from './helpers.ts'
import type { MockApi, MockApiOptions } from './mockApi.ts'

// Every screen and state of #36 at 360×640 and 1280×800: each test opens the state, saves a
// full-page screenshot (light mode) and runs the checks of the criteria (helpers.ts).

interface Screen {
  /** The screen and state; the screenshot is "<name>-<size>.png". */
  name: string
  /** A state that exists only at one width. */
  only?: Size
  session: SessionKind
  api?: MockApiOptions
  path: string
  /** Something that shows once the page has loaded. */
  ready: (page: Page) => Locator
  /** Brings the loaded page into the state. */
  act?: (page: Page, api: MockApi, size: Size) => Promise<void>
  /** False for a state that shows a spinner on purpose. */
  settle?: boolean
}

const heading = (name: string) => (page: Page) => page.getByRole('heading', { level: 1, name })

const ENTRY_TEXT = 'Ran the first workshop on writing good incident reviews; twelve people from four teams came.'
const SUGGESTION: MockApiOptions['suggestion'] = {
  category: 'Achievement',
  tags: ['workshops', 'incident-reviews', 'knowledge-sharing'],
}

const REVIEW_RESULTS = '/review?start_date=2026-09-01&end_date=2026-11-13'

async function chooseCategory(page: Page, category: string) {
  await page.getByRole('group', { name: 'Category' }).getByRole('button', { name: category }).click()
}

async function openFold(page: Page) {
  await page.getByRole('button', { name: 'Add tags and result' }).click()
}

async function draftSummary(page: Page) {
  await page.getByRole('button', { name: 'Draft summary' }).click()
}

const SCREENS: Screen[] = [
  // Logged out
  {
    name: 'login-empty',
    session: 'none',
    path: '/login',
    ready: heading('Log in'),
  },
  {
    name: 'login-failed',
    session: 'none',
    api: { rejectLogin: true },
    path: '/login',
    ready: heading('Log in'),
    act: async (page) => {
      await page.getByLabel('Email').fill('alex@example.com')
      await page.getByLabel('Password', { exact: true }).fill('not-the-password')
      await page.getByRole('button', { name: 'Log in' }).click()
      await expect(page.getByRole('alert').filter({ hasText: /\S/ }).first()).toBeVisible()
    },
  },
  {
    name: 'register-empty',
    session: 'none',
    path: '/register',
    ready: heading('Create an account'),
  },
  {
    name: 'register-field-errors',
    session: 'none',
    path: '/register',
    ready: heading('Create an account'),
    act: async (page) => {
      await page.getByLabel('Email').fill('alex@')
      await page.getByLabel('Password', { exact: true }).fill('short')
      await page.getByRole('button', { name: 'Create account' }).click()
      await expect(page.locator('.field__message').first()).toBeVisible()
    },
  },
  {
    name: 'not-found-logged-out',
    session: 'none',
    path: '/no-such-page',
    ready: heading('Page not found'),
  },

  // App shell
  {
    name: 'more-menu-open',
    only: 'phone',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/',
    ready: heading('Entries'),
    act: async (page) => {
      await page.getByRole('button', { name: 'More' }).click()
      await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
    },
  },
  {
    name: 'not-found-logged-in',
    session: 'user',
    path: '/no-such-page',
    ready: heading('Page not found'),
  },

  // Entries
  {
    name: 'entries-empty',
    session: 'user',
    path: '/',
    ready: (page) => page.locator('.empty-state'),
  },
  {
    name: 'entries-with-nudge',
    session: 'user',
    api: { entries: ENTRIES_WITH_NUDGE },
    path: '/',
    ready: (page) => page.locator('.entries-page__nudge'),
  },
  {
    name: 'entries-without-nudge',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/',
    ready: (page) => page.locator('.entry-row').first(),
    act: async (page) => {
      await expect(page.locator('.entries-page__nudge')).toHaveCount(0)
    },
  },
  {
    name: 'entries-delete-dialog',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/',
    ready: (page) => page.locator('.entry-row').first(),
    act: async (page) => {
      await page.getByRole('button', { name: /^Delete entry from/ }).first().click()
      await expect(page.getByRole('dialog', { name: 'Delete this entry?' })).toBeVisible()
    },
  },
  {
    name: 'entries-load-error',
    session: 'user',
    api: { failEntryList: true },
    path: '/',
    ready: (page) => page.getByRole('button', { name: 'Try again' }),
  },

  // Entry form
  {
    name: 'new-entry-empty',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
  },
  {
    name: 'new-entry-text-missing',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByRole('button', { name: 'Save entry' }).click()
      await expect(page.locator('.field__message').first()).toBeVisible()
    },
  },
  {
    name: 'new-entry-tags-open',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await openFold(page)
      const tags = page.getByRole('combobox', { name: 'Tags' })
      for (const tag of ['billing', 'mentoring', 'quarterly-goals']) {
        await tags.fill(tag)
        await tags.press('Enter')
      }
      await expect(page.getByRole('list', { name: 'Added tags' }).getByRole('listitem')).toHaveCount(3)
      // The list of matching known tags opens under the input.
      await tags.fill('pre')
      await expect(page.getByRole('listbox', { name: 'Matching tags' })).toBeVisible()
    },
  },
  {
    name: 'new-entry-suggestions',
    session: 'user',
    api: { suggestion: SUGGESTION },
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await page.getByRole('button', { name: 'Suggest category and tags' }).click()
      await expect(page.getByRole('button', { name: 'Discard suggestions' })).toBeVisible()
    },
  },
  {
    name: 'new-entry-suggested-other-category',
    session: 'user',
    api: { suggestion: SUGGESTION },
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await chooseCategory(page, 'Learning')
      await page.getByRole('button', { name: 'Suggest category and tags' }).click()
      await expect(page.getByRole('button', { name: 'Suggested: Achievement' })).toBeVisible()
    },
  },
  {
    name: 'new-entry-saved',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await chooseCategory(page, 'Achievement')
      await page.getByRole('button', { name: 'Save entry' }).click()
      await expect(page.getByText('Entry saved.')).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Just saved' })).toBeVisible()
    },
  },
  {
    name: 'new-entry-near-limit',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(longText(1950))
      await expect(page.locator('.field__counter')).toBeVisible()
    },
  },
  {
    name: 'new-entry-over-limit',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(longText(2040))
      await expect(page.locator('.field__counter')).toBeVisible()
    },
  },
  {
    name: 'edit-entry-loaded',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: `/entries/${EDIT_ENTRY.id}/edit`,
    ready: (page) => page.getByLabel('What happened?'),
  },
  {
    name: 'edit-entry-discard-dialog',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: `/entries/${EDIT_ENTRY.id}/edit`,
    ready: (page) => page.getByLabel('What happened?'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(`${EDIT_ENTRY.text} Changed.`)
      await page.getByRole('button', { name: 'Cancel' }).click()
      await expect(page.getByRole('dialog', { name: 'Discard changes?' })).toBeVisible()
    },
  },
  {
    name: 'edit-entry-missing',
    session: 'user',
    path: `/entries/${MISSING_ID}/edit`,
    ready: (page) => page.getByText("This entry doesn't exist."),
  },

  // Review
  {
    name: 'review-filters-closed',
    only: 'phone',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/review',
    ready: (page) => page.locator('.review-page__total').filter({ hasText: /entr/ }),
  },
  {
    name: 'review-filters-in-use',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: `${REVIEW_RESULTS}&category=Achievement&tag=billing`,
    ready: (page) => page.locator('.review-page__total').filter({ hasText: /entr/ }),
    act: async (page, _api, size) => {
      if (size === 'phone') {
        await page.getByRole('button', { name: /^Filters/ }).click()
      }
      await expect(page.getByRole('button', { name: 'Clear filters' })).toBeVisible()
    },
  },
  {
    name: 'review-results-panel-idle',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: REVIEW_RESULTS,
    ready: (page) => page.locator('.review-page__category').first(),
    act: async (page) => {
      await expect(page.getByRole('button', { name: 'Draft summary' })).toBeEnabled()
    },
  },
  {
    name: 'review-no-match',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: `${REVIEW_RESULTS}&category=Learning&tag=billing`,
    ready: (page) => page.getByText('No entries match these filters.'),
  },
  {
    name: 'review-no-entries',
    session: 'user',
    path: '/review',
    ready: (page) => page.getByText('No entries yet. Write your first win.'),
  },
  {
    name: 'review-panel-drafting',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE, holdDraft: true },
    path: REVIEW_RESULTS,
    ready: (page) => page.locator('.review-page__category').first(),
    settle: false,
    act: async (page) => {
      await draftSummary(page)
      await expect(page.locator('.summary-panel__progress')).not.toBeEmpty()
    },
  },
  {
    name: 'review-panel-draft',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: REVIEW_RESULTS,
    ready: (page) => page.locator('.review-page__category').first(),
    act: async (page) => {
      await draftSummary(page)
      await expect(page.getByRole('button', { name: 'Save summary' })).toBeVisible()
    },
  },

  // Summaries
  {
    name: 'summaries-empty',
    session: 'user',
    path: '/summaries',
    ready: (page) => page.getByText('No summaries yet. Draft one on the Review page.'),
  },
  {
    name: 'summaries-rows',
    session: 'user',
    api: { summaries: SUMMARIES },
    path: '/summaries',
    ready: (page) => page.locator('.summary-row').first(),
  },
  {
    name: 'summary-loaded',
    session: 'user',
    api: { summaries: SUMMARIES },
    path: `/summaries/${LONG_SUMMARY.id}`,
    ready: (page) => page.getByRole('button', { name: 'Save summary' }),
  },
  {
    name: 'summary-delete-dialog',
    session: 'user',
    api: { summaries: SUMMARIES },
    path: `/summaries/${LONG_SUMMARY.id}`,
    ready: (page) => page.getByRole('button', { name: 'Save summary' }),
    act: async (page) => {
      await page.getByRole('button', { name: 'Delete', exact: true }).click()
      await expect(page.getByRole('dialog', { name: 'Delete this summary?' })).toBeVisible()
    },
  },
  {
    name: 'summary-missing',
    session: 'user',
    path: `/summaries/${MISSING_ID}`,
    ready: (page) => page.getByText("This summary doesn't exist."),
  },

  // Settings
  {
    name: 'settings-default',
    session: 'user',
    path: '/settings',
    ready: (page) => page.getByRole('button', { name: 'Delete account' }),
  },
  {
    name: 'settings-delete-step',
    session: 'user',
    path: '/settings',
    ready: (page) => page.getByRole('button', { name: 'Delete account' }),
    act: async (page) => {
      await page.getByRole('button', { name: 'Delete account' }).click()
      await expect(page.getByRole('heading', { name: 'Delete your account?' })).toBeVisible()
    },
  },

  // Demo session
  {
    name: 'demo-entries',
    session: 'demo',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/',
    ready: (page) => page.locator('.entry-row').first(),
  },
  {
    name: 'demo-new-entry-saved',
    session: 'demo',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await chooseCategory(page, 'Feedback')
      await page.getByRole('button', { name: 'Save entry' }).click()
      await expect(page.getByText('Entry saved.')).toBeVisible()
    },
  },
  {
    name: 'demo-review-panel',
    session: 'demo',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: REVIEW_RESULTS,
    ready: (page) => page.locator('.review-page__category').first(),
    act: async (page) => {
      await draftSummary(page)
      await expect(page.getByRole('button', { name: 'Save summary' })).toBeVisible()
    },
  },
  {
    name: 'demo-settings',
    session: 'demo',
    path: '/settings',
    ready: (page) => page.getByText("The demo account can't be deleted."),
    act: async (page) => {
      await expect(page.getByRole('button', { name: 'Delete account' })).toHaveCount(0)
    },
  },
]

/** Text of exactly `length` characters, in words, for the character counter states. */
function longText(length: number): string {
  const words = 'Helped the support team close the backlog of customer questions before the release. '
  return words.repeat(Math.ceil(length / words.length)).slice(0, length)
}

for (const screen of SCREENS) {
  test(screen.name, async ({ page }, testInfo) => {
    const size = sizeOf(testInfo)
    test.skip(screen.only !== undefined && screen.only !== size, `only at ${screen.only} width`)
    const api = await prepare(page, screen.session, screen.api)
    await page.goto(screen.path)
    await expect(screen.ready(page)).toBeVisible()
    if (screen.session === 'demo') {
      await expect(page.locator('.demo-notice')).toBeVisible()
    }
    await screen.act?.(page, api, size)
    if (screen.settle !== false) {
      await settle(page)
    }
    await screenshot(page, screen.name, size)
    await checkScreen(page, size)
    expectOnlyMockedRequests(page, api)
  })
}
