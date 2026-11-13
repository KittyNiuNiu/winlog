import { readFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

// End-to-end smoke test (#37, product-spec.md §9 and §10.2): the main user flow against a
// running Winlog with the mock AI provider. Register, write an entry, review it, draft,
// edit and save a summary, export, log out. Every run uses a new account and a new tag,
// so it can run again and again on the same database. Only Playwright's built-in waiting
// (locators and web-first assertions), no fixed sleeps.

const NUDGE_TEXT = 'Did something go well? Even a small win is worth writing down.'
const EMPTY_ENTRIES_TEXT = 'No entries yet. Write your first win.'

/** A short value no other run has used: the time in base 36 and a random part. */
function uniqueSuffix(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** Waits until the page shows `pathname`. */
async function expectPath(page: Page, pathname: string): Promise<void> {
  await expect(page).toHaveURL((url) => url.pathname === pathname)
}

/** The shape of the parts of the JSON export (openapi.yaml, ExportFile) the test reads. */
interface ExportFile {
  entries: { text: string; category: string; date: string; tags: string[] }[]
  summaries: { text: string }[]
}

test('test_smoke_register_capture_review_summarise_export_log_out', async ({ page }) => {
  const suffix = uniqueSuffix()
  const email = `e2e-${suffix}@example.com`
  // #6: at least 10 characters, with an uppercase letter, a number and a special character.
  const password = 'Smoke-Test-2026!'
  const entryText = `Smoke test ${suffix}: shipped the release checklist a day early.`
  const tag = `e2e-${suffix}`
  const addedSentence = `Edited by the smoke test ${suffix}.`
  const nav = page.getByRole('navigation', { name: 'Main' })
  const main = page.getByRole('main')
  let today = ''

  await test.step('register (#26, #6) and land on the entries page', async () => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { level: 1, name: 'Create an account' })).toBeVisible()
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Create account' }).click()
    await expectPath(page, '/')
    await expect(page.getByRole('heading', { level: 1, name: 'Entries' })).toBeVisible()
    await expect(nav.getByRole('button', { name: 'Log out' })).toBeVisible()
  })

  await test.step('the new account sees the nudge and the empty state (#30)', async () => {
    await expect(main.getByText(NUDGE_TEXT, { exact: true })).toBeVisible()
    await expect(main.getByText(EMPTY_ENTRIES_TEXT, { exact: true })).toBeVisible()
  })

  await test.step('write an entry with a category and a new tag (#27, FR-E1 to FR-E3)', async () => {
    await nav.getByRole('link', { name: 'New entry' }).click()
    await expectPath(page, '/entries/new')
    await expect(page.getByRole('heading', { level: 1, name: 'New entry' })).toBeVisible()

    // "Today" is what the form fills in, so the browser's time zone cannot disagree with it.
    const date = page.getByLabel('Date', { exact: true })
    await expect(date).toHaveValue(/^\d{4}-\d{2}-\d{2}$/)
    today = await date.inputValue()

    await page.getByLabel('What happened?').fill(entryText)
    await page.getByRole('group', { name: 'Category' }).getByRole('button', { name: 'Achievement' }).click()
    await page.getByRole('button', { name: 'Add tags and result' }).click()
    const tags = page.getByRole('combobox', { name: 'Tags' })
    await tags.fill(tag)
    await tags.press('Enter')
    await expect(page.getByRole('list', { name: 'Added tags' }).getByRole('listitem')).toHaveText([tag])

    await page.getByRole('button', { name: 'Save entry' }).click()
    await expect(page.getByText('Entry saved.', { exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Just saved' }).getByText(entryText)).toBeVisible()
    await expectPath(page, '/entries/new')
  })

  await test.step('the entries page lists the entry and no longer shows the nudge (FR-N1)', async () => {
    await nav.getByRole('link', { name: 'Entries' }).click()
    await expectPath(page, '/')
    await expect(main.getByText(entryText)).toBeVisible()
    await expect(page.getByText(NUDGE_TEXT)).toHaveCount(0)
  })

  await test.step('review the entry by period and tag (#31, FR-R1, FR-R2)', async () => {
    await nav.getByRole('link', { name: 'Review' }).click()
    await expectPath(page, '/review')
    await expect(page.getByRole('heading', { level: 1, name: 'Review' })).toBeVisible()

    await page.getByLabel('Start date').fill(today)
    await page.getByLabel('End date').fill(today)
    const tagFilter = page.getByRole('combobox', { name: 'Tags' })
    await tagFilter.fill(tag)
    await page.getByRole('option', { name: tag, exact: true }).click()
    await expect(page.getByRole('list', { name: 'Selected tags' }).getByRole('listitem')).toHaveText([tag])

    // The filter is in the URL, and the results for it have loaded.
    await expect(page).toHaveURL((url) => {
      const params = url.searchParams
      return params.get('start_date') === today && params.get('end_date') === today && params.getAll('tag').includes(tag)
    })
    await expect(page.getByText('Loading entries…')).toHaveCount(0)

    await expect(page.getByRole('status').filter({ hasText: /^1 entry$/ })).toBeVisible()
    const achievements = page.getByRole('region', { name: 'Achievement 1 entry' })
    await expect(achievements.getByRole('heading', { level: 2 })).toHaveText('Achievement 1 entry')
    await expect(achievements.getByText(entryText)).toBeVisible()
  })

  const mockText = () => `Mock summary of 1 entry from ${today} to ${today}.`
  const editedText = () => `${mockText()} ${addedSentence}`

  await test.step('draft, edit and save a summary (#32, FR-R3 to FR-R5)', async () => {
    const panel = page.getByRole('region', { name: 'Summary', exact: true })
    await panel.getByRole('button', { name: 'Draft summary' }).click()
    const field = panel.getByLabel('Summary text')
    await expect(field).toHaveValue(mockText())
    await field.fill(editedText())
    await panel.getByRole('button', { name: 'Save summary' }).click()
    await expect(panel.getByText('Summary saved.', { exact: true })).toBeVisible()
  })

  await test.step('the summaries list holds exactly the edited summary (#33)', async () => {
    await nav.getByRole('link', { name: 'Summaries' }).click()
    await expectPath(page, '/summaries')
    await expect(page.getByRole('heading', { level: 1, name: 'Summaries' })).toBeVisible()
    const rows = main.getByRole('listitem')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText(editedText())
  })

  await test.step('export the data as JSON (#34, FR-D1)', async () => {
    await nav.getByRole('link', { name: 'Settings' }).click()
    await expectPath(page, '/settings')
    const yourData = page.getByRole('region', { name: 'Your data' })
    const downloading = page.waitForEvent('download')
    await yourData.getByRole('button', { name: 'Download JSON' }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toMatch(/^winlog-export-\d{4}-\d{2}-\d{2}\.json$/)

    const exported = JSON.parse(await readFile(await download.path(), 'utf-8')) as ExportFile
    expect(exported.entries).toHaveLength(1)
    expect(exported.entries[0]).toMatchObject({ text: entryText, category: 'Achievement', date: today, tags: [tag] })
    expect(exported.summaries).toHaveLength(1)
    expect(exported.summaries[0].text).toBe(editedText())
  })

  await test.step('log out, and the entries page then needs a login again (FR-A2)', async () => {
    await nav.getByRole('button', { name: 'Log out' }).click()
    await expectPath(page, '/login')
    await expect(page.getByRole('heading', { level: 1, name: 'Log in' })).toBeVisible()
    await page.goto('/')
    await expectPath(page, '/login')
    await expect(page.getByRole('heading', { level: 1, name: 'Log in' })).toBeVisible()
  })
})
