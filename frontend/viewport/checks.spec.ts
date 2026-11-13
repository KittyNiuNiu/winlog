import { expect, test, type Locator, type Page } from '@playwright/test'
import { ENTRIES_WITHOUT_NUDGE, LONG_SUMMARY, SUMMARIES } from './data.ts'
import { expectOnlyMockedRequests, prepare, screenshot, settle, sizeOf } from './helpers.ts'
import type { EntryInput } from './mockApi.ts'
import { SCREENSHOT_DIR, TODAY } from './settings.ts'

// The checks of #36 that need one particular screen: quick capture on the phone, the
// login buttons in the first screen, the review page's gap and summary panel, the focus
// look of every text field in light and dark mode, and the demo link's focus outline.

const REVIEW_RESULTS = '/review?start_date=2026-09-01&end_date=2026-11-13'

async function box(locator: Locator) {
  const value = await locator.boundingBox()
  if (value === null) {
    throw new Error('element has no box')
  }
  return value
}

test.describe('quick capture (§3, FR-E1)', () => {
  test.use({ hasTouch: true })

  test('test_fr_e1_capture_from_entries_is_text_category_save_on_the_phone', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'phone', 'quick capture is checked at 360×640')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE })
    await page.goto('/')
    await page.getByRole('main').getByRole('link', { name: 'New entry' }).tap()
    await expect(page.getByRole('heading', { level: 1, name: 'New entry' })).toBeVisible()

    await page.getByLabel('What happened?').fill('Fixed the flaky release pipeline before the demo.')
    await page.getByRole('group', { name: 'Category' }).getByRole('button', { name: 'Achievement' }).tap()
    // No other step: the date stays today and "Add tags and result" stays closed.
    await expect(page.getByLabel('Date')).toHaveValue(TODAY)
    const fold = page.getByRole('button', { name: 'Add tags and result' })
    await expect(fold).toHaveAttribute('aria-expanded', 'false')

    const sent = page.waitForRequest((request) => request.method() === 'POST' && request.url().endsWith('/entries'))
    await page.getByRole('button', { name: 'Save entry' }).tap()
    const body = (await sent).postDataJSON() as EntryInput
    expect(body).toMatchObject({
      text: 'Fixed the flaky release pipeline before the demo.',
      category: 'Achievement',
      date: TODAY,
      tags: [],
    })
    await expect(page.getByText('Entry saved.')).toBeVisible()
    await expect(fold).toHaveAttribute('aria-expanded', 'false')
    await screenshot(page, 'quick-capture-saved', 'phone')
    expectOnlyMockedRequests(page, api)
  })
})

test('test_fr_x1_login_and_demo_buttons_are_in_the_first_phone_screen', async ({ page }, testInfo) => {
  test.skip(sizeOf(testInfo) !== 'phone', 'checked at 360×640')
  const api = await prepare(page, 'none')
  await page.goto('/login')
  await settle(page)
  for (const name of ['Log in', 'Try the demo']) {
    const button = await box(page.getByRole('button', { name, exact: true }))
    expect(button.y, `${name}: top`).toBeGreaterThanOrEqual(0)
    expect(button.y + button.height, `${name}: bottom inside the first 640px`).toBeLessThanOrEqual(640)
  }
  expectOnlyMockedRequests(page, api)
})

test.describe('review page from 48rem (#31 design review)', () => {
  /** Bottom of the "Review" title's box to the top of the filter area. */
  async function titleGap(page: Page) {
    const title = await box(page.getByRole('heading', { level: 1, name: 'Review' }))
    const filters = await box(page.locator('.review-page__filters'))
    return filters.y - (title.y + title.height)
  }

  test('test_review_filters_start_24px_below_the_title_at_1024_and_1280', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'laptop', 'laptop widths')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE })
    for (const viewport of [
      { width: 1024, height: 768 },
      { width: 1280, height: 800 },
    ]) {
      await page.setViewportSize(viewport)
      await page.goto(REVIEW_RESULTS)
      await expect(page.locator('.review-page__category').first()).toBeVisible()
      await settle(page)
      expect(await titleGap(page), `gap at ${viewport.width}×${viewport.height}`).toBeCloseTo(24, 1)
      const panel = await box(page.locator('.summary-panel'))
      const filters = await box(page.locator('.review-page__filters'))
      if (viewport.width === 1280) {
        expect(panel.y, 'panel top level with the filter area').toBeCloseTo(filters.y, 1)
      } else {
        // Below 75rem the panel stays below the results.
        expect(panel.y).toBeGreaterThan(filters.y + filters.height)
      }
      await screenshot(page, 'review-gap', `${viewport.width}x${viewport.height}`)
    }
    expectOnlyMockedRequests(page, api)
  })

  test('test_review_phone_keeps_16px_below_the_title', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'phone', 'phone')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE })
    await page.goto(REVIEW_RESULTS)
    await settle(page)
    const title = await box(page.getByRole('heading', { level: 1, name: 'Review' }))
    const toggle = await box(page.getByRole('button', { name: /^Filters/ }))
    expect(toggle.y - (title.y + title.height)).toBeCloseTo(16, 1)
    expectOnlyMockedRequests(page, api)
  })

  test('test_fr_r3_laptop_panel_with_a_draft_sits_right_of_the_results', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'laptop', 'laptop')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE })
    await page.goto(REVIEW_RESULTS)
    await page.getByRole('button', { name: 'Draft summary' }).click()
    const save = page.getByRole('button', { name: 'Save summary' })
    await expect(save).toBeVisible()
    await settle(page)
    const panelLocator = page.locator('.summary-panel')
    const panel = await box(panelLocator)
    const results = await box(page.locator('.review-page__results'))
    const filters = await box(page.locator('.review-page__filters'))
    expect(panel.x, 'panel to the right of the results').toBeGreaterThanOrEqual(results.x + results.width)
    expect(panel.y, 'panel top level with the filter area').toBeCloseTo(filters.y, 1)
    expect(panel.height, 'panel no taller than the window minus 48px').toBeLessThanOrEqual(800 - 48)

    // Save summary is reachable by scrolling inside the panel.
    await panelLocator.evaluate((element) => {
      element.scrollTop = element.scrollHeight
    })
    const button = await box(save)
    const shown = await box(panelLocator)
    expect(button.y).toBeGreaterThanOrEqual(shown.y)
    expect(button.y + button.height).toBeLessThanOrEqual(shown.y + shown.height)
    const hit = await save.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      const target = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
      return target !== null && element.contains(target)
    })
    expect(hit, 'Save summary is not covered').toBe(true)
    expectOnlyMockedRequests(page, api)
  })
})

/** DESIGN.md → Colors and Elevation: Plum and Focus glow in each colour scheme. */
const FOCUS_LOOK = {
  light: { border: 'rgb(122, 46, 104)', shadow: 'rgb(246, 221, 235) 0px 0px 0px 3px' },
  dark: { border: 'rgb(231, 163, 207)', shadow: 'rgba(231, 163, 207, 0.3) 0px 0px 0px 3px' },
} as const

async function expectFocusLook(field: Locator, scheme: keyof typeof FOCUS_LOOK, name: string) {
  await field.focus()
  await expect(field, `${name} has focus`).toBeFocused()
  const look = await field.evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      border: [style.borderTopColor, style.borderRightColor, style.borderBottomColor, style.borderLeftColor],
      shadow: style.boxShadow,
    }
  })
  expect(look.border, `${name}: plum border`).toEqual(Array(4).fill(FOCUS_LOOK[scheme].border))
  expect(look.shadow, `${name}: focus glow`).toBe(FOCUS_LOOK[scheme].shadow)
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`focus look of text fields, ${scheme} mode (DESIGN.md → Inputs)`, () => {
    test.use({ colorScheme: scheme })

    test(`test_text_fields_show_plum_border_and_focus_glow_${scheme}`, async ({ page }) => {
      const api = await prepare(page, 'none', { entries: ENTRIES_WITHOUT_NUDGE, summaries: SUMMARIES })

      for (const path of ['/login', '/register']) {
        await page.goto(path)
        await expectFocusLook(page.getByLabel('Email'), scheme, `${path} email`)
        await expectFocusLook(page.getByLabel('Password', { exact: true }), scheme, `${path} password`)
      }

      // Log in through the form, so the rest of the pages are open.
      await page.goto('/login')
      await page.getByLabel('Email').fill('alex@example.com')
      await page.getByLabel('Password', { exact: true }).fill('Correct-Horse-7')
      await page.getByRole('button', { name: 'Log in', exact: true }).click()
      await expect(page.getByRole('heading', { level: 1, name: 'Entries' })).toBeVisible()

      await page.goto('/entries/new')
      await expectFocusLook(page.getByLabel('What happened?'), scheme, 'entry text')
      await expectFocusLook(page.getByLabel('Date'), scheme, 'entry date')
      await page.getByRole('button', { name: 'Add tags and result' }).click()
      await expectFocusLook(page.getByRole('combobox', { name: 'Tags' }), scheme, 'tag input')
      await expectFocusLook(page.getByLabel('Result'), scheme, 'result')

      await page.goto(REVIEW_RESULTS)
      await expect(page.locator('.review-page__category').first()).toBeVisible()
      const filtersToggle = page.getByRole('button', { name: /^Filters/ })
      if (await filtersToggle.isVisible()) {
        await filtersToggle.click()
      }
      await expectFocusLook(page.getByLabel('Start date'), scheme, 'review start date')
      await expectFocusLook(page.getByLabel('End date'), scheme, 'review end date')
      await expectFocusLook(page.locator('.review-page__tags input'), scheme, 'review tag filter')
      await page.getByRole('button', { name: 'Draft summary' }).click()
      await expectFocusLook(page.locator('.summary-panel textarea'), scheme, 'summary panel text')

      await page.goto(`/summaries/${LONG_SUMMARY.id}`)
      await expectFocusLook(page.getByLabel('Summary text'), scheme, 'summary page text')

      await page.goto('/settings')
      await page.getByRole('button', { name: 'Delete account' }).click()
      await expectFocusLook(page.getByLabel('Current password'), scheme, 'current password')
      await expectFocusLook(page.getByLabel('Type "delete" to confirm'), scheme, 'confirm word')
      expectOnlyMockedRequests(page, api)
    })
  })

  test.describe(`demo link focus outline, ${scheme} mode (#35 design review, note 2)`, () => {
    test.use({ colorScheme: scheme })

    test(`test_fr_x1_demo_link_focus_outline_clears_the_notice_text_${scheme}`, async ({ page }, testInfo) => {
      test.skip(sizeOf(testInfo) !== 'laptop', 'checked on the laptop')
      const api = await prepare(page, 'demo', { entries: ENTRIES_WITHOUT_NUDGE })
      await page.goto('/')
      await settle(page)
      // Keyboard focus: from "Log out", the last control of the sidebar, Tab goes to the link.
      await page.getByRole('button', { name: 'Log out' }).focus()
      await page.keyboard.press('Tab')
      const link = page.getByRole('link', { name: 'Create your own account' })
      await expect(link).toBeFocused()
      const geometry = await link.evaluate((element) => {
        const style = getComputedStyle(element)
        const text = element.parentElement!.querySelector('.demo-notice__text')!
        // The bottom of the text line's box (its last line), and the link's box.
        return {
          textBottom: text.getBoundingClientRect().bottom,
          linkTop: element.getBoundingClientRect().top,
          outlineStyle: style.outlineStyle,
          outlineWidth: parseFloat(style.outlineWidth),
          outlineOffset: parseFloat(style.outlineOffset),
        }
      })
      expect(geometry.outlineStyle, 'a visible focus outline').toBe('solid')
      const outlineTop = geometry.linkTop - geometry.outlineOffset - geometry.outlineWidth
      expect(outlineTop - geometry.textBottom, 'space between the outline and the text line').toBeGreaterThan(0)
      await page.locator('.demo-notice').screenshot({
        path: `${SCREENSHOT_DIR}/demo-link-focus-${scheme}-laptop.png`,
        animations: 'disabled',
      })
      expectOnlyMockedRequests(page, api)
    })
  })
}
