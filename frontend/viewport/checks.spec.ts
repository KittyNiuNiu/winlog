import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  ENTRIES_WITH_ONE_LINE,
  ENTRIES_WITHOUT_NUDGE,
  LONG_ENTRY,
  LONG_SUMMARY,
  ONE_LINE_ENTRY,
  SUMMARIES,
  TWENTY_FILTER_TAGS,
} from './data.ts'
import {
  contrast,
  expectControlsNotCovered,
  expectNoSidewaysScroll,
  expectOnlyMockedRequests,
  looksOf,
  prepare,
  screenshot,
  screenshotAround,
  settle,
  sizeOf,
  tokenColour,
  VISIBLY_DIFFERENT,
  type Looks,
} from './helpers.ts'
import type { EntryInput, MockApiOptions } from './mockApi.ts'
import { SCREENSHOT_DIR, TODAY } from './settings.ts'

// The checks of #36 that need one particular screen: quick capture on the phone, the
// login buttons in the first screen, the review page's gap and summary panel, the focus
// look of every text field in light and dark mode, and the demo link's focus outline.
// From #90: the hover and disabled fills in each colour scheme, and the entry rows at
// 768, 1024 and 1280px.

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

test.describe('the full tag filter (#88 design note)', () => {
  test('test_fr_r1_note_sits_4px_under_the_hint_and_12px_above_the_chips', async ({ page }, testInfo) => {
    const size = sizeOf(testInfo)
    const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE })
    const tags = TWENTY_FILTER_TAGS.map((tag) => `tag=${encodeURIComponent(tag)}`).join('&')
    await page.goto(`${REVIEW_RESULTS}&${tags}`)
    await expect(page.locator('.review-page__total')).toHaveText(/entr/)
    if (size === 'phone') {
      await page.getByRole('button', { name: /^Filters/ }).click()
    }
    const note = page.getByText('Up to 20 tags in a filter. Remove one to add another.')
    await expect(note).toBeVisible()
    await settle(page)

    const field = page.getByRole('combobox', { name: 'Tags' })
    const hint = page.getByText('Shows entries with any of the selected tags')
    const hintBox = await box(hint)
    const noteBox = await box(note)
    const chipsBox = await box(page.getByRole('list', { name: 'Selected tags' }))
    expect(noteBox.y - (hintBox.y + hintBox.height), 'note 4px under the hint').toBeCloseTo(4, 1)
    expect(chipsBox.y - (noteBox.y + noteBox.height), 'chips 12px under the note').toBeCloseTo(12, 1)
    expect((await box(field)).height, 'search field keeps its tap target').toBeGreaterThanOrEqual(48)
    // Muted like the hint: no error colour, and the field is not invalid.
    const colours = await Promise.all([note, hint].map((each) => each.evaluate((el) => getComputedStyle(el).color)))
    expect(colours[0]).toBe(colours[1])
    await expect(field).toHaveAttribute('aria-invalid', 'false')
    // One line on the laptop; it may wrap on the phone.
    if (size === 'laptop') {
      expect(noteBox.height).toBeLessThan(30)
    }

    // The search field takes typing but offers nothing.
    await field.fill('a')
    await field.press('ArrowDown')
    await field.press('Enter')
    await expect(field).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('option')).toHaveCount(0)
    await expect(page.getByRole('list', { name: 'Selected tags' }).getByRole('listitem')).toHaveCount(20)
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

// Hover and disabled fills in each colour scheme (#90, criteria A and B).

/** How a control shows hover: a secondary button, a quiet text action or an entry row icon. */
type HoverKind = 'secondary' | 'quiet' | 'icon'

interface HoverControl {
  /** For the screenshot, "hover-<name>-<scheme>-<size>.png". */
  name: string
  control: Locator
  kind: HoverKind
  /** Light mode only: the hover fill may equal the surface (accepted in criterion A). */
  lightSurfaceExempt?: boolean
}

interface HoverState {
  name: string
  api?: MockApiOptions
  path: string
  /** Brings the page into the state, returns the controls to hover. */
  open: (page: Page) => Promise<HoverControl[]>
}

const ENTRY_TEXT = 'Ran the first workshop on writing good incident reviews; twelve people from four teams came.'

const HOVER_STATES: HoverState[] = [
  {
    name: 'entries',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: '/',
    open: async (page) => {
      await expect(page.locator('.entry-row').first()).toBeVisible()
      const controls: HoverControl[] = [
        { name: 'edit', control: page.getByRole('link', { name: /^Edit entry from/ }).first(), kind: 'icon' },
        { name: 'delete', control: page.getByRole('button', { name: /^Delete entry from/ }).first(), kind: 'icon' },
      ]
      if (await page.locator('.shell__new-entry').isVisible()) {
        // In light mode its hover fill is like the sidebar's; its Plum border shows the hover.
        controls.push({
          name: 'sidebar-new-entry',
          control: page.locator('.shell__new-entry'),
          kind: 'secondary',
          lightSurfaceExempt: true,
        })
      }
      return controls
    },
  },
  {
    name: 'new-entry',
    api: { suggestion: { category: 'Achievement', tags: ['workshops', 'incident-reviews'] } },
    path: '/entries/new',
    open: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'New entry' })).toBeVisible()
      // Learning chosen, so the suggestion shows "Suggested: Achievement" as a quiet action.
      await page.getByLabel('What happened?').fill(ENTRY_TEXT)
      await page.getByRole('group', { name: 'Category' }).getByRole('button', { name: 'Learning' }).click()
      await page.getByRole('button', { name: 'Suggest category and tags' }).click()
      await expect(page.getByRole('button', { name: 'Discard suggestions' })).toBeVisible()
      return [
        { name: 'add-tags-and-result', control: page.getByRole('button', { name: 'Add tags and result' }), kind: 'secondary' },
        { name: 'discard-suggestions', control: page.getByRole('button', { name: 'Discard suggestions' }), kind: 'quiet' },
        { name: 'suggested-category', control: page.getByRole('button', { name: 'Suggested: Achievement' }), kind: 'quiet' },
      ]
    },
  },
  {
    name: 'review',
    api: { entries: ENTRIES_WITHOUT_NUDGE },
    path: REVIEW_RESULTS,
    open: async (page) => {
      await expect(page.locator('.review-page__category').first()).toBeVisible()
      const draft = page.locator('.summary-panel').getByRole('button', { name: 'Draft summary' })
      await expect(draft).toBeEnabled()
      return [{ name: 'draft-summary', control: draft, kind: 'secondary' }]
    },
  },
  {
    name: 'settings',
    path: '/settings',
    open: async (page) => {
      await page.getByRole('button', { name: 'Delete account' }).click()
      const step = page.locator('.settings-page__step')
      await expect(step).toBeVisible()
      return [{ name: 'delete-step-cancel', control: step.getByRole('button', { name: 'Cancel' }), kind: 'secondary' }]
    },
  },
]

async function restingLooks(page: Page, control: Locator): Promise<Looks> {
  await control.scrollIntoViewIfNeeded()
  await page.mouse.move(0, 0)
  return looksOf(control)
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`hover fills, ${scheme} mode (#90, criterion A)`, () => {
    test.use({ colorScheme: scheme })

    for (const state of HOVER_STATES) {
      test(`test_hover_fill_differs_from_rest_and_surface_on_${state.name}_${scheme}`, async ({ page }, testInfo) => {
        const size = sizeOf(testInfo)
        const api = await prepare(page, 'user', state.api)
        await page.goto(state.path)
        const controls = await state.open(page)
        await settle(page)
        const hoverFill = await tokenColour(page, '--color-secondary-hover')
        const plum = await tokenColour(page, '--color-plum')
        if (scheme === 'dark') {
          expect(hoverFill, 'the dark Secondary hover fill').toBe('rgb(46, 38, 45)')
        } else {
          expect(hoverFill, 'light mode as today: Peach wash').toBe(await tokenColour(page, '--color-peach-wash'))
        }

        for (const { name, control, kind, lightSurfaceExempt } of controls) {
          const rest = await restingLooks(page, control)
          await control.hover()
          const hover = await looksOf(control)
          expect(hover.fill, `${name}: the Secondary hover fill`).toBe(hoverFill)
          expect(contrast(hover.fill, rest.fill), `${name}: hover against rest`).toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
          if (!(lightSurfaceExempt === true && scheme === 'light')) {
            expect(contrast(hover.fill, hover.surface), `${name}: hover against its surface`).toBeGreaterThanOrEqual(
              VISIBLY_DIFFERENT,
            )
          }
          expect(contrast(hover.color, hover.fill), `${name}: its text or icon on the hover fill`).toBeGreaterThanOrEqual(4.5)
          if (kind === 'secondary') {
            expect(rest.border, `${name}: Field border at rest`).not.toEqual(Array(4).fill(plum))
            expect(hover.border, `${name}: Plum border on hover`).toEqual(Array(4).fill(plum))
          } else if (kind === 'icon') {
            expect(rest.color, `${name}: Muted plum-grey icon at rest`).toBe(await tokenColour(page, '--color-muted-plum-grey'))
            expect(hover.color, `${name}: Plum icon on hover`).toBe(plum)
          } else {
            expect(hover.color, `${name}: Plum text`).toBe(plum)
          }
          await screenshotAround(page, [control], `hover-${name}-${scheme}-${size}`)
          await page.mouse.move(0, 0)
        }
        expectOnlyMockedRequests(page, api)
      })
    }
  })

  test.describe(`disabled fills, ${scheme} mode (#90, criterion B)`, () => {
    test.use({ colorScheme: scheme })

    /** The disabled look (DESIGN.md → Buttons), and no change on hover. */
    async function expectDisabledLook(page: Page, button: Locator, name: string): Promise<Looks> {
      await expect(button, name).toBeDisabled()
      const looks = await restingLooks(page, button)
      expect(looks.fill, `${name}: the Disabled fill`).toBe(await tokenColour(page, '--color-disabled-fill'))
      expect(looks.color, `${name}: Muted plum-grey text`).toBe(await tokenColour(page, '--color-muted-plum-grey'))
      expect(looks.border, `${name}: Field border`).toEqual(Array(4).fill(await tokenColour(page, '--color-field-border')))
      expect(looks.shadow, `${name}: no shadow`).toBe('none')
      expect(looks.cursor, `${name}: not-allowed cursor`).toBe('not-allowed')
      expect(contrast(looks.color, looks.fill), `${name}: text on the Disabled fill`).toBeGreaterThanOrEqual(4.5)
      for (const token of ['--color-paper-white', '--color-blush-white']) {
        expect(contrast(looks.fill, await tokenColour(page, token)), `${name}: against ${token}`).toBeGreaterThanOrEqual(
          VISIBLY_DIFFERENT,
        )
      }
      if (scheme === 'dark') {
        expect(looks.fill, `${name}: the dark Disabled fill`).toBe('rgb(46, 38, 45)')
      } else {
        expect(looks.fill, `${name}: light mode as today, Peach wash`).toBe(await tokenColour(page, '--color-peach-wash'))
      }
      // No hover change on a disabled button.
      const box = await button.boundingBox()
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
      const hovered = await looksOf(button)
      expect([hovered.fill, hovered.border], `${name}: no hover change`).toEqual([looks.fill, looks.border])
      await page.mouse.move(0, 0)
      return looks
    }

    test(`test_disabled_suggest_differs_from_the_ready_fold_button_${scheme}`, async ({ page }, testInfo) => {
      const size = sizeOf(testInfo)
      const api = await prepare(page, 'user')
      await page.goto('/entries/new')
      await settle(page)
      const suggest = page.getByRole('button', { name: 'Suggest category and tags' })
      const fold = page.getByRole('button', { name: 'Add tags and result' })
      const disabled = await expectDisabledLook(page, suggest, 'Suggest category and tags')
      await expect(fold).toBeEnabled()
      const ready = await restingLooks(page, fold)
      expect(ready.fill, 'the ready button has Paper white').toBe(await tokenColour(page, '--color-paper-white'))
      expect(contrast(disabled.fill, ready.fill), 'disabled against ready').toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
      expect(contrast(disabled.fill, disabled.surface), 'disabled against the page').toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
      await screenshotAround(page, [suggest, fold], `disabled-new-entry-${scheme}-${size}`, { fullPage: true })
      expectOnlyMockedRequests(page, api)
    })

    test(`test_disabled_delete_my_account_differs_from_cancel_and_the_step_${scheme}`, async ({ page }, testInfo) => {
      const size = sizeOf(testInfo)
      const api = await prepare(page, 'user')
      await page.goto('/settings')
      await page.getByRole('button', { name: 'Delete account' }).click()
      const step = page.locator('.settings-page__step')
      await expect(step).toBeVisible()
      await settle(page)
      // Before the password and "delete" are typed.
      const remove = step.getByRole('button', { name: 'Delete my account' })
      const cancel = step.getByRole('button', { name: 'Cancel' })
      const disabled = await expectDisabledLook(page, remove, 'Delete my account')
      const ready = await restingLooks(page, cancel)
      const panel = await looksOf(step)
      expect(panel.own, 'the step is a Paper white panel').toBe(await tokenColour(page, '--color-paper-white'))
      expect(disabled.surface, 'the button sits on the step').toBe(panel.own)
      expect(contrast(disabled.fill, ready.fill), 'disabled against Cancel').toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
      expect(contrast(disabled.fill, panel.own), 'disabled against the step').toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
      await screenshotAround(page, [step], `disabled-settings-delete-step-${scheme}-${size}`, { fullPage: true })
      expectOnlyMockedRequests(page, api)
    })

    test(`test_ready_draft_summary_has_the_secondary_resting_fill_${scheme}`, async ({ page }, testInfo) => {
      const size = sizeOf(testInfo)
      const api = await prepare(page, 'user', { entries: ENTRIES_WITHOUT_NUDGE, holdDraft: true })
      await page.goto(REVIEW_RESULTS)
      await expect(page.locator('.review-page__category').first()).toBeVisible()
      await settle(page)
      const panel = page.locator('.summary-panel')
      const draft = panel.getByRole('button', { name: 'Draft summary' })
      await expect(draft).toBeEnabled()
      const ready = await restingLooks(page, draft)
      const paperWhite = await tokenColour(page, '--color-paper-white')
      const disabledFill = await tokenColour(page, '--color-disabled-fill')
      expect(ready.fill, 'Paper white, the secondary resting fill').toBe(paperWhite)
      expect(ready.fill, 'not the Disabled fill').not.toBe(disabledFill)
      expect(contrast(ready.fill, disabledFill), 'ready against disabled').toBeGreaterThanOrEqual(VISIBLY_DIFFERENT)
      expect(ready.border, 'Field border').toEqual(Array(4).fill(await tokenColour(page, '--color-field-border')))
      await screenshotAround(page, [panel], `ready-draft-summary-${scheme}-${size}`, { fullPage: true })

      // Busy (#84) keeps the normal colours, and hover changes nothing.
      await draft.click()
      const busy = panel.locator('button[aria-busy="true"]')
      await expect(busy).toBeVisible()
      const busyLooks = await restingLooks(page, busy)
      expect([busyLooks.fill, busyLooks.color], 'busy keeps its normal colours').toEqual([ready.fill, ready.color])
      await busy.hover()
      const busyHover = await looksOf(busy)
      expect([busyHover.fill, busyHover.border], 'no hover change while busy').toEqual([busyLooks.fill, busyLooks.border])
      await page.mouse.move(0, 0)
      await api.releaseDraft()
      await expect(panel.getByRole('button', { name: 'Save summary' })).toBeVisible()
      expectOnlyMockedRequests(page, api)
    })
  })
}

// The entry rows from 48rem (#90, criterion D): from 64rem Edit and Delete take a fourth
// column, so a one-line row is 59px; at 768px the text column keeps its 224px.

interface RowGeometry {
  text: string
  row: DOMRect
  date: DOMRect
  label: DOMRect
  body: DOMRect
  /** The text paragraph: its first line box starts at its top, 24px tall like the date's. */
  paragraph: DOMRect
  edit: DOMRect
  remove: DOMRect
  labelJustify: string
}

async function rowGeometry(page: Page): Promise<RowGeometry[]> {
  return page.locator('.entries-page .entry-row').evaluateAll((rows) =>
    rows.map((row) => {
      const box = (selector: string) => row.querySelector(selector)!.getBoundingClientRect().toJSON() as DOMRect
      const [action, other] = row.querySelectorAll('.entry-row__action')
      return {
        text: row.querySelector('.entry-row__text')!.textContent ?? '',
        row: row.getBoundingClientRect().toJSON() as DOMRect,
        date: box('.entry-row__date'),
        label: box('.category-label'),
        body: box('.entry-row__body'),
        paragraph: box('.entry-row__text'),
        edit: action.getBoundingClientRect().toJSON() as DOMRect,
        remove: other.getBoundingClientRect().toJSON() as DOMRect,
        labelJustify: getComputedStyle(row.querySelector('.category-label')!).justifySelf,
      }
    }),
  )
}

function overlaps(a: DOMRect, b: DOMRect): boolean {
  return a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5
}

/** Every row: the date on the first line of text, 44px actions that cover nothing. */
function expectRows(rows: RowGeometry[], width: number) {
  expect(rows.length).toBeGreaterThan(0)
  for (const row of rows) {
    const name = `${row.text.slice(0, 30)}… at ${width}px`
    // Both have a 24px line, so the same top puts the date on the text's first line.
    expect(row.date.height, `${name}: one 24px date line`).toBeCloseTo(24, 0)
    expect(Math.abs(row.date.top - row.paragraph.top), `${name}: the date on the first line`).toBeLessThanOrEqual(0.5)
    for (const action of [row.edit, row.remove]) {
      expect([action.width, action.height], `${name}: 44×44 actions`).toEqual([44, 44])
      expect(overlaps(action, row.body), `${name}: the actions do not cover the text`).toBe(false)
      expect(action.right, `${name}: inside the row`).toBeLessThanOrEqual(row.row.right + 0.5)
    }
  }
}

test.describe('entry rows from 48rem (#90, criterion D)', () => {
  test('test_fr_e4_one_line_row_is_at_most_77px_at_1280x800', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'laptop', 'checked at 1280×800')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITH_ONE_LINE })
    await page.goto('/')
    await expect(page.getByText(ONE_LINE_ENTRY.text)).toBeVisible()
    await settle(page)
    const rows = await rowGeometry(page)
    const row = rows.find(({ text }) => text === ONE_LINE_ENTRY.text)!
    expect(row.paragraph.height, 'one line of text').toBeCloseTo(24, 0)
    expect(row.row.height, 'at most 77px with its hairline').toBeLessThanOrEqual(77)
    expect(row.row.height, 'the design note: 59px').toBeCloseTo(59, 0)
    // Date | label | text | Edit and Delete, on one line: the actions centred on the label's line.
    expect(row.edit.top, 'the actions on the label line').toBeCloseTo(row.label.top - 9, 0)
    expect(row.edit.left, 'the actions after the text column').toBeGreaterThanOrEqual(row.body.right + 16 - 0.5)
    expect(row.remove.right, 'Delete ends at the row edge').toBeCloseTo(row.row.right, 0)
    expect(row.body.width, 'the text column at 1280').toBeCloseTo(624, 0)
    // The label keeps its own width: its tint does not fill the 120px column.
    expect(row.labelJustify).toBe('start')
    expect(row.label.width).toBeLessThan(120)
    expectRows(rows, 1280)
    // The long entry: the Result and ten tags wrap inside the text column.
    const long = rows.find(({ text }) => text === LONG_ENTRY.text)!
    expect(long.row.height).toBeGreaterThan(77)
    await expectNoSidewaysScroll(page)
    await expectControlsNotCovered(page)
    const oneLine = page.locator('.entry-row', { hasText: ONE_LINE_ENTRY.text })
    await screenshotAround(page, [oneLine], 'entry-row-one-line-1280x800', { fullPage: true })
    await screenshot(page, 'entries-rows', '1280x800')
    expectOnlyMockedRequests(page, api)
  })

  test('test_fr_e4_rows_at_768x1024_and_1024x768_keep_the_text_column_and_cover_nothing', async ({ page }, testInfo) => {
    test.skip(sizeOf(testInfo) !== 'laptop', 'laptop widths')
    const api = await prepare(page, 'user', { entries: ENTRIES_WITH_ONE_LINE })
    for (const [viewport, column] of [
      [{ width: 768, height: 1024 }, 224],
      [{ width: 1024, height: 768 }, 368],
    ] as const) {
      await page.setViewportSize(viewport)
      await page.goto('/')
      await expect(page.getByText(ONE_LINE_ENTRY.text)).toBeVisible()
      await settle(page)
      const rows = await rowGeometry(page)
      for (const row of rows) {
        expect(row.body.width, `the text column at ${viewport.width}px`).toBeGreaterThanOrEqual(224)
        expect(row.body.width, `the text column at ${viewport.width}px`).toBeCloseTo(column, 0)
      }
      if (viewport.width === 768) {
        // Below 64rem the actions stay 8px under the label in the 120px column.
        const row = rows.find(({ text }) => text === ONE_LINE_ENTRY.text)!
        expect(row.edit.top - row.label.bottom).toBeCloseTo(8, 0)
      }
      expectRows(rows, viewport.width)
      await expectNoSidewaysScroll(page)
      await expectControlsNotCovered(page)
      await screenshot(page, 'entries-rows', `${viewport.width}x${viewport.height}`)
    }
    expectOnlyMockedRequests(page, api)
  })
})
