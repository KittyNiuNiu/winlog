import { expect, type Page, type TestInfo } from '@playwright/test'
import { MockApi, TOKEN_EXPIRES_AT, type MockApiOptions } from './mockApi.ts'
import { API_BASE_URL, NOW, SCREENSHOT_DIR } from './settings.ts'

// Shared steps of the viewport tests (#36): open the app with a fixed clock, a mocked API
// and a stored session, then check a screen and save its screenshot.

export type Size = 'phone' | 'laptop'

/** Who is logged in: nobody, a normal user, or the shared demo account (#35). */
export type SessionKind = 'none' | 'user' | 'demo'

/** The project's size: "phone" (360×640) or "laptop" (1280×800), see playwright.config.ts. */
export function sizeOf(testInfo: TestInfo): Size {
  const name = testInfo.project.name
  if (name !== 'phone' && name !== 'laptop') {
    throw new Error(`unknown project ${name}`)
  }
  return name
}

const SESSION_KEY = 'winlog.session'

/**
 * Prepares a page: the fixed clock, the mocked API, and the session in localStorage (as
 * after a login, src/api/session.ts). Any request that is neither to the preview server
 * nor to the mocked API fails the test.
 */
export async function prepare(page: Page, session: SessionKind, options: MockApiOptions = {}): Promise<MockApi> {
  const api = new MockApi(options)
  const stray: string[] = []
  await page.clock.setFixedTime(NOW)
  await page.route(
    (url) => url.origin !== new URL(API_BASE_URL).origin && url.hostname !== 'localhost',
    (route) => {
      stray.push(route.request().url())
      return route.abort()
    },
  )
  await api.install(page)
  if (session !== 'none') {
    const value = JSON.stringify({ token: `${session}-token`, expiresAt: TOKEN_EXPIRES_AT, demo: session === 'demo' })
    // Only before the first page load, so a logout in the test is not undone by a reload.
    await page.addInitScript(
      ([key, stored]) => {
        if (window.sessionStorage.getItem('viewport.session-set') === null) {
          window.sessionStorage.setItem('viewport.session-set', '1')
          window.localStorage.setItem(key, stored)
        }
      },
      [SESSION_KEY, value] as const,
    )
  }
  strayRequests.set(page, stray)
  return api
}

const strayRequests = new WeakMap<Page, string[]>()

/** Fails when the page sent a request the tests do not answer. */
export function expectOnlyMockedRequests(page: Page, api: MockApi): void {
  expect(strayRequests.get(page) ?? [], 'requests outside the app and the mocked API').toEqual([])
  expect(api.unanswered, 'API requests the mock has no answer for').toEqual([])
}

/** Waits until the web fonts are in and nothing is loading, so the layout is final. */
export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await expect(page.locator('.spinner:not(.summary-panel .spinner)')).toHaveCount(0)
}

/** Saves a full-page screenshot named after the screen, the state and the size. */
export async function screenshot(page: Page, name: string, size: Size | string): Promise<void> {
  // No hover look where the pointer happened to stop.
  await page.mouse.move(0, 0)
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/${name}-${size}.png`,
    fullPage: true,
    animations: 'disabled',
    caret: 'hide',
  })
}

/**
 * The links the criteria exempt from the 44px rule, each only where its paragraph or
 * message holds other words too. Every other link is measured, also a link alone in its
 * line such as "Go to your entries" or the demo notice's "Create your own account".
 */
export const INLINE_LINKS = ['Create an account', 'Log in', 'Log in instead', 'Back to entries', 'Back to summaries']

interface ControlProblem {
  control: string
  width: number
  height: number
}

/**
 * Every check the criteria make on every screen and state at this size, except the ones
 * people make by looking at the screenshots.
 */
export async function checkScreen(page: Page, size: Size): Promise<void> {
  await expectNoSidewaysScroll(page)
  await expectLayout(page, size)
  if (size === 'phone') {
    await expectTapTargets(page)
    await expectPhoneDialogs(page)
  } else {
    await expectLaptopWidths(page)
  }
  await expectControlsNotCovered(page)
}

export async function expectNoSidewaysScroll(page: Page): Promise<void> {
  const { scrollWidth, width } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }))
  expect(scrollWidth, 'the page scrolls sideways').toBeLessThanOrEqual(width)
}

/** Phone: one column, 20px side padding, the phone header and no sidebar. Laptop: the sidebar. */
export async function expectLayout(page: Page, size: Size): Promise<void> {
  const layout = await page.evaluate(() => {
    const shell = document.querySelector('.shell')
    const auth = document.querySelector('.auth')
    const padded = shell === null ? auth : document.querySelector('.shell__main')
    const style = padded === null ? null : getComputedStyle(padded)
    const header = document.querySelector<HTMLElement>('.shell__header')
    const headerBox = header?.getBoundingClientRect()
    return {
      shell: shell === null ? null : shell.classList.contains('shell--laptop') ? 'laptop' : 'phone',
      auth: auth !== null,
      paddingLeft: style?.paddingLeft ?? null,
      paddingRight: style?.paddingRight ?? null,
      header: headerBox === undefined ? null : { width: headerBox.width, height: headerBox.height, top: headerBox.top },
      mainLeft: document.querySelector('.shell__main')?.getBoundingClientRect().left ?? null,
    }
  })
  expect(layout.shell !== null || layout.auth, 'the app shell or the login layout').toBe(true)
  if (layout.shell === null) {
    if (size === 'phone') {
      expect([layout.paddingLeft, layout.paddingRight]).toEqual(['20px', '20px'])
    }
    return
  }
  expect(layout.shell, 'the shell for this width').toBe(size)
  if (size === 'phone') {
    expect([layout.paddingLeft, layout.paddingRight], 'phone side padding').toEqual(['20px', '20px'])
    // The header runs across the top, above the content: no sidebar beside it.
    expect(layout.header?.width).toBe(await page.evaluate(() => document.documentElement.clientWidth))
    expect(layout.mainLeft).toBe(0)
  } else {
    // The sidebar at the left; the content starts to its right.
    expect(layout.header?.width).toBe(232)
    expect(layout.mainLeft).toBe(232)
  }
}

/**
 * Phone: every control that is not a link inside a line of text is at least 44×44 CSS px.
 * Read-only chips, the count badge and category labels are not controls, so they are
 * not in the selector. Returns the exempt links it found.
 */
export async function expectTapTargets(page: Page): Promise<string[]> {
  const { problems, inline } = await page.evaluate((inlineNames) => {
    const selector = 'a[href], button, input:not([type="hidden"]), select, textarea, [role="button"], [role="option"]'
    const problems: { control: string; width: number; height: number }[] = []
    const inline: string[] = []
    for (const element of document.querySelectorAll<HTMLElement>(selector)) {
      if (element.closest('[hidden], .visually-hidden') !== null) continue
      const style = getComputedStyle(element)
      if (style.visibility === 'hidden' || style.display === 'none') continue
      // Not shown in the page: inside a closed dialog, or behind an open modal dialog.
      const dialog = element.closest('dialog')
      if (dialog !== null && !dialog.open) continue
      const openModal = document.querySelector('dialog[open]')
      if (openModal !== null && dialog === null) continue
      const box = element.getBoundingClientRect()
      if (box.width === 0 && box.height === 0) continue
      const name = (element.getAttribute('aria-label') ?? element.textContent ?? '').trim() || element.outerHTML.slice(0, 80)
      if (element.tagName === 'A' && inlineNames.includes(name)) {
        // Exempt only inside a line of text: its paragraph or message holds other words too.
        const line = element.closest('p, .message')
        if (line !== null && (line.textContent ?? '').trim() !== name) {
          inline.push(name)
          continue
        }
      }
      if (box.width < 44 - 0.01 || box.height < 44 - 0.01) {
        problems.push({ control: name, width: Math.round(box.width * 10) / 10, height: Math.round(box.height * 10) / 10 })
      }
    }
    return { problems, inline }
  }, INLINE_LINKS)
  expect(problems satisfies ControlProblem[], 'controls under 44×44px on the phone').toEqual([])
  return inline
}

/** Phone: an open dialog is at least 20px from each side, with stacked full-width buttons. */
export async function expectPhoneDialogs(page: Page): Promise<void> {
  const dialogs = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLDialogElement>('dialog[open]')].map((dialog) => {
      const box = dialog.getBoundingClientRect()
      const style = getComputedStyle(dialog)
      const contentWidth = dialog.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
      const buttons = [...dialog.querySelectorAll('button')].map((button) => {
        const rect = button.getBoundingClientRect()
        return { top: rect.top, bottom: rect.bottom, width: rect.width }
      })
      return { left: box.left, right: window.innerWidth - box.right, contentWidth, buttons }
    }),
  )
  for (const dialog of dialogs) {
    expect(dialog.left, 'dialog to the left edge').toBeGreaterThanOrEqual(20)
    expect(dialog.right, 'dialog to the right edge').toBeGreaterThanOrEqual(20)
    expect(dialog.buttons.length).toBeGreaterThan(0)
    dialog.buttons.forEach((button, index) => {
      expect(button.width, 'dialog button at full width').toBeCloseTo(dialog.contentWidth, 0)
      if (index > 0) {
        expect(button.top, 'dialog buttons stacked').toBeGreaterThanOrEqual(dialog.buttons[index - 1].bottom)
      }
    })
  }
}

/**
 * Laptop: the content area is at most 64rem (1024px) wide, and every paragraph, entry text
 * and summary text is at most 68ch at its own font size.
 */
export async function expectLaptopWidths(page: Page): Promise<void> {
  const { areas, lines } = await page.evaluate(() => {
    const areas = [...document.querySelectorAll<HTMLElement>('#main > *, .auth__column')].map((element) => ({
      element: element.className,
      width: element.getBoundingClientRect().width,
    }))
    // 68ch at the element's own font, as CSS works it out: a box 68ch wide inside it.
    const probe = document.createElement('span')
    probe.style.cssText = 'position:absolute;display:block;width:68ch;height:0;padding:0;border:0;visibility:hidden'
    const lines: { element: string; width: number; limit: number }[] = []
    const texts = document.querySelectorAll<HTMLElement>(
      'p, .entry-row__text, .summary-row__preview, .summary-page textarea, .summary-panel textarea',
    )
    for (const element of texts) {
      if (element.closest('[hidden], .visually-hidden') !== null) continue
      const box = element.getBoundingClientRect()
      if (box.width === 0) continue
      const style = getComputedStyle(element)
      let width: number
      if (element instanceof HTMLTextAreaElement) {
        // The lines can fill the field's content box.
        width =
          box.width -
          parseFloat(style.paddingLeft) -
          parseFloat(style.paddingRight) -
          parseFloat(style.borderLeftWidth) -
          parseFloat(style.borderRightWidth)
        probe.style.font = style.font
        probe.style.fontVariantNumeric = style.fontVariantNumeric
        element.parentElement!.appendChild(probe)
      } else {
        // The width the text's lines take, not the box: a banner may be wider than its text.
        const range = document.createRange()
        range.selectNodeContents(element)
        width = range.getBoundingClientRect().width
        probe.style.font = ''
        probe.style.fontVariantNumeric = ''
        element.appendChild(probe)
      }
      const limit = probe.getBoundingClientRect().width
      probe.remove()
      if (width > limit + 0.5) {
        lines.push({ element: `${element.tagName.toLowerCase()}.${element.className}`, width, limit })
      }
    }
    return { areas, lines }
  })
  for (const area of areas) {
    expect(area.width, `content area ${area.element}`).toBeLessThanOrEqual(1024)
  }
  expect(lines, 'text lines wider than 68ch').toEqual([])
}

/**
 * No control is covered by something else: the element at its centre is the control or
 * inside it. With a modal dialog open, only the dialog's controls are checked.
 */
export async function expectControlsNotCovered(page: Page): Promise<void> {
  const covered = await page.evaluate(() => {
    const scrollX = window.scrollX
    const scrollY = window.scrollY
    const selector = 'a[href], button, input:not([type="hidden"]), select, textarea, [role="option"]'
    const openModal = document.querySelector('dialog[open]')
    const root = openModal ?? document
    const problems: string[] = []
    for (const element of root.querySelectorAll<HTMLElement>(selector)) {
      if (element.closest('[hidden], .visually-hidden, .shell__skip-link') !== null) continue
      const dialog = element.closest('dialog')
      if (dialog !== null && !dialog.open) continue
      if (element.getClientRects().length === 0) continue
      element.scrollIntoView({ block: 'center', inline: 'center' })
      // The first box: a link that wraps has one per line.
      const box = element.getClientRects()[0]
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)
      const label = hit instanceof HTMLLabelElement ? hit.control : null
      // An open list of matching tags covers what is below it, as intended.
      const openList = hit?.closest('[role="listbox"]') ?? null
      if (hit === null || (hit !== element && !element.contains(hit) && label !== element && openList === null)) {
        const name = (element.getAttribute('aria-label') ?? element.textContent ?? '').trim()
        problems.push(`${name || element.outerHTML.slice(0, 80)} is covered by ${hit?.outerHTML.slice(0, 80)}`)
      }
    }
    window.scrollTo(scrollX, scrollY)
    return problems
  })
  expect(covered, 'controls covered by something else').toEqual([])
}
