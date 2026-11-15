import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  EDIT_ENTRY,
  ENTRIES_WITHOUT_NUDGE,
  ENTRIES_WITH_NUDGE,
  LONG_SUMMARY,
  MISSING_ID,
  SUMMARIES,
  TWENTY_FILTER_TAGS,
} from './data.ts'
import {
  checkScreen,
  contrast,
  expectNudgeSurface,
  expectOnlyMockedRequests,
  looksOf,
  prepare,
  screenshot,
  settle,
  sizeOf,
  VISIBLY_DIFFERENT,
  type SessionKind,
  type Size,
} from './helpers.ts'
import type { FieldError, MockApi, MockApiOptions } from './mockApi.ts'

// Every screen and state of #36 at 360×640 and 1280×800: each test opens the state, saves a
// full-page screenshot (light mode) and runs the checks of the criteria (helpers.ts). The
// screens #90 changes are also taken in dark mode, as "<name>-dark-<size>.png".

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
  /** Also in dark mode (#90), saved as "<name>-dark-<size>.png". */
  dark?: boolean
}

const heading = (name: string) => (page: Page) => page.getByRole('heading', { level: 1, name })

const ENTRY_TEXT = 'Ran the first workshop on writing good incident reviews; twelve people from four teams came.'
const SUGGESTION: MockApiOptions['suggestion'] = {
  category: 'Achievement',
  tags: ['workshops', 'incident-reviews', 'knowledge-sharing'],
}
/** A full entry (#43), with none of SUGGESTION's tags. */
const TEN_TAGS = [
  'billing',
  'mentoring',
  'quarterly-goals',
  'onboarding',
  'release',
  'support',
  'docs',
  'hiring',
  'security',
  'on-call',
]

const REVIEW_RESULTS = '/review?start_date=2026-09-01&end_date=2026-11-13'

// A 422 `validation_failed` naming email and password, with the backend's reasons (#72).
const EMAIL_REASON =
  'value is not a valid email address: The part after the @-sign is not valid. It should have a period.'
const LOGIN_FIELD_ERRORS: FieldError[] = [
  { field: 'email', reason: EMAIL_REASON },
  { field: 'password', reason: 'String should have at most 128 characters' },
]
const REGISTER_FIELD_ERRORS: FieldError[] = [
  { field: 'email', reason: EMAIL_REASON },
  { field: 'password', reason: 'Password contains an invalid character (an unpaired surrogate).' },
]

/**
 * Sends the form with an address the form lets through and the backend rejects, then waits
 * until the page shows its own texts under both fields and the cursor is in Email (#72).
 * `form` is the fields' id prefix: "login" or "register".
 */
async function sendRejectedForm(
  page: Page,
  { form, password, button, passwordText }: { form: string; password: string; button: string; passwordText: string },
) {
  const email = page.getByLabel('Email')
  const passwordField = page.getByLabel('Password', { exact: true })
  await email.fill('alice@invalid')
  await passwordField.fill(password)
  await page.getByRole('button', { name: button, exact: true }).click()
  await expect(email).toBeFocused()
  await expect(page.locator(`#${form}-email-messages`)).toHaveText('Enter a valid email address, such as name@example.com.')
  await expect(page.locator(`#${form}-password-messages`)).toHaveText(passwordText)
  await expect(email).toHaveAttribute('aria-invalid', 'true')
  await expect(passwordField).toHaveAttribute('aria-invalid', 'true')
  // No form alert, and no server text anywhere in the page, attributes included.
  await expect(page.locator('.form__alert')).toHaveText('')
  const html = await page.content()
  const reasons = [...LOGIN_FIELD_ERRORS, ...REGISTER_FIELD_ERRORS].map(({ reason }) => reason)
  for (const serverText of ['The request has invalid fields.', ...reasons]) {
    expect(html, 'server text in the page').not.toContain(serverText)
  }
  // The messages wrap inside the form column.
  const column = await page.locator('form').boundingBox()
  expect(column).not.toBeNull()
  for (const message of await page.locator('.field__message').all()) {
    const box = await message.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x, 'message inside the form column').toBeGreaterThanOrEqual(column!.x)
    expect(box!.x + box!.width, 'message inside the form column').toBeLessThanOrEqual(column!.x + column!.width + 0.5)
  }
}

async function chooseCategory(page: Page, category: string) {
  await page.getByRole('group', { name: 'Category' }).getByRole('button', { name: category }).click()
}

async function openFold(page: Page) {
  await page.getByRole('button', { name: 'Add tags and result' }).click()
}

/**
 * The suggestion notice shows `text` (#86): the info message under the suggest row, with
 * the text wrapped inside it, and Save entry is still the only filled plum element.
 */
async function expectSuggestionNotice(page: Page, text: string) {
  const notice = page.locator('.entry-form__notice')
  await expect(notice).toHaveText(text)
  await expect(notice).toHaveAttribute('role', 'status')
  await expect(notice).toHaveClass(/message--info/)
  const fits = await notice.evaluate((element) => element.scrollWidth <= element.clientWidth)
  expect(fits, 'the notice text wraps inside the message').toBe(true)
  await expect(page.locator('.button--primary')).toHaveCount(1)
  await expect(page.locator('.button--primary')).toHaveText('Save entry')
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
    // #72: a 422 naming email and password shows the page's own texts, the cursor in Email.
    name: 'login-server-errors',
    session: 'none',
    api: { loginFieldErrors: LOGIN_FIELD_ERRORS },
    path: '/login',
    ready: heading('Log in'),
    act: (page) =>
      sendRejectedForm(page, {
        form: 'login',
        // 129 characters: login checks no password rule, so the form sends it.
        password: `Ab1!${'x'.repeat(125)}`,
        button: 'Log in',
        passwordText: 'Check your password. It can have at most 128 characters.',
      }),
  },
  {
    name: 'register-server-errors',
    session: 'none',
    api: { registerFieldErrors: REGISTER_FIELD_ERRORS },
    path: '/register',
    ready: heading('Create an account'),
    act: (page) =>
      sendRejectedForm(page, {
        form: 'register',
        password: 'Correct-Horse-7',
        button: 'Create account',
        passwordText: "This password can't be used. Choose a different one.",
      }),
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
    dark: true,
    act: async (page) => {
      await expectNudgeSurface(page)
    },
  },
  {
    // #90: the nudge and the info message "This entry was already deleted." together. They
    // differ by their surface, not only by the icon and their place.
    name: 'entries-nudge-and-notice',
    session: 'user',
    api: { entries: ENTRIES_WITH_NUDGE, entryAlreadyDeleted: true },
    path: '/',
    ready: (page) => page.locator('.entries-page__nudge'),
    dark: true,
    act: async (page) => {
      await page.getByRole('button', { name: /^Delete entry from/ }).first().click()
      const dialog = page.getByRole('dialog', { name: 'Delete this entry?' })
      await dialog.getByRole('button', { name: 'Delete entry' }).click()
      await expect(dialog).toBeHidden()
      const notice = page.locator('.entries-page__notice')
      await expect(notice).toHaveText('This entry was already deleted.')
      await expect(page.locator('.entries-page__nudge')).toBeVisible()
      const nudge = await expectNudgeSurface(page)
      const message = await looksOf(notice)
      expect(contrast(nudge.fill, message.fill), 'the nudge against the info message').toBeGreaterThanOrEqual(
        VISIBLY_DIFFERENT,
      )
      expect(message.textAlign).not.toBe('center')
      expect(message.radius).toBe('12px')
      await expect(notice.locator('svg')).toHaveCount(1)
      await expect(page.locator('.entries-page__nudge svg')).toHaveCount(0)
    },
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
    dark: true,
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
    // #86: the mock's default answer ({ category: 'Achievement', tags: [] }) after choosing
    // Achievement brings nothing new. The shared SUGGESTION would bring new tags.
    name: 'new-entry-no-new-suggestions',
    session: 'user',
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await chooseCategory(page, 'Achievement')
      await page.getByRole('button', { name: 'Suggest category and tags' }).click()
      await expectSuggestionNotice(page, 'No new suggestions for this text.')
      await expect(page.getByRole('button', { name: 'Discard suggestions' })).toHaveCount(0)
    },
  },
  {
    // #86: 10 tags on the entry, then SUGGESTION, whose 3 tags are all new: none is added.
    name: 'new-entry-suggestions-tag-limit',
    session: 'user',
    api: { suggestion: SUGGESTION },
    path: '/entries/new',
    ready: heading('New entry'),
    act: async (page) => {
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await openFold(page)
      const tags = page.getByRole('combobox', { name: 'Tags' })
      await tags.fill(`${TEN_TAGS.join(',')},`)
      const added = page.getByRole('list', { name: 'Added tags' }).getByRole('listitem')
      await expect(added).toHaveCount(10)
      await page.getByRole('button', { name: 'Suggest category and tags' }).click()
      await expectSuggestionNotice(page, 'Up to 10 tags per entry, so not every suggested tag was added.')
      await expect(added).toHaveCount(10)
      // Nothing under the tag input, and no error state: the entry is valid.
      await expect(page.locator('#entry-tags-messages')).toBeEmpty()
      await expect(tags).toHaveAttribute('aria-invalid', 'false')
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
    // #88: the tag filter holds as many tags as it can, with its note. The phone panel is open.
    name: 'review-tag-filter-full',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: `${REVIEW_RESULTS}&${TWENTY_FILTER_TAGS.map((tag) => `tag=${encodeURIComponent(tag)}`).join('&')}`,
    ready: (page) => page.locator('.review-page__total').filter({ hasText: /entr/ }),
    act: async (page, _api, size) => {
      if (size === 'phone') {
        await page.getByRole('button', { name: /^Filters/ }).click()
      }
      await expect(page.getByText('Up to 20 tags in a filter. Remove one to add another.')).toBeVisible()
      await expect(page.getByRole('list', { name: 'Selected tags' }).getByRole('listitem')).toHaveCount(20)
    },
  },
  {
    name: 'review-results-panel-idle',
    session: 'user',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: REVIEW_RESULTS,
    ready: (page) => page.locator('.review-page__category').first(),
    dark: true,
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
    dark: true,
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

/** Opens the screen's state, saves its screenshot as "<shot>-<size>.png" and runs the checks. */
async function runScreen(page: Page, size: Size, screen: Screen, shot: string) {
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
  await screenshot(page, shot, size)
  await checkScreen(page, size)
  expectOnlyMockedRequests(page, api)
}

for (const screen of SCREENS) {
  test(screen.name, async ({ page }, testInfo) => {
    await runScreen(page, sizeOf(testInfo), screen, screen.name)
  })
}

test.describe('dark mode (#90)', () => {
  test.use({ colorScheme: 'dark' })

  for (const screen of SCREENS.filter(({ dark }) => dark === true)) {
    test(`${screen.name}-dark`, async ({ page }, testInfo) => {
      await runScreen(page, sizeOf(testInfo), screen, `${screen.name}-dark`)
    })
  }
})
