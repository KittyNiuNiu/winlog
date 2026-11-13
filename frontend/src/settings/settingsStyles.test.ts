// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Checks on the settings page's stylesheet that jsdom cannot measure (#34 and its design
// note): the one column, buttons stacked on the phone and in a row from 48rem, the flat
// confirmation panel, every control at least 44px, and nothing that pushes the page
// sideways at 360px. node:fs is loaded by name because the app's TypeScript setup has no
// Node types.

interface NodeFs {
  readFileSync(path: URL, encoding: 'utf8'): string
}

const fs = (await import(/* @vite-ignore */ `node:${'fs'}`)) as NodeFs

function css(path: string): string {
  return fs.readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
}

/** The declarations of `selector` in a block of CSS (the first rule for it). */
function rule(block: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(block)
  if (match === null) {
    throw new Error(`no rule for ${selector}`)
  }
  return match[1] ?? ''
}

/** The body of the `@media (min-width: <width>)` block. */
function media(block: string, width: string): string {
  const start = block.indexOf(`@media (min-width: ${width})`)
  if (start < 0) {
    throw new Error(`no media block for ${width}`)
  }
  const open = block.indexOf('{', start)
  let depth = 0
  for (let index = open; index < block.length; index += 1) {
    if (block[index] === '{') {
      depth += 1
    } else if (block[index] === '}') {
      depth -= 1
      if (depth === 0) {
        return block.slice(open + 1, index)
      }
    }
  }
  throw new Error(`unclosed media block for ${width}`)
}

const pageCss = css('../pages/SettingsPage.css')
const buttonCss = css('../components/Button.css')
const fieldCss = css('../components/TextField.css')

describe('settings page styles (#34)', () => {
  it('test_fr_d1_page_is_one_column_at_most_68ch_that_wraps_long_words', () => {
    const page = rule(pageCss, '.settings-page')
    expect(page).toContain('max-width: var(--measure)')
    expect(page).toContain('min-width: 0')
    expect(page).toContain('overflow-wrap: anywhere')
  })

  it('test_fr_d1_buttons_are_full_width_and_stacked_on_the_phone_and_in_a_row_from_48rem', () => {
    expect(rule(pageCss, '.settings-page__buttons')).toContain('flex-direction: column')
    expect(rule(pageCss, '.settings-page__buttons .button')).toContain('width: 100%')
    const laptop = media(pageCss, '48rem')
    expect(rule(laptop, '.settings-page__buttons')).toContain('flex-direction: row')
    expect(rule(laptop, '.settings-page__buttons')).toContain('flex-wrap: wrap')
    expect(rule(laptop, '.settings-page__buttons .button')).toContain('width: auto')
  })

  it('test_fr_d2_step_is_a_flat_panel_that_never_scrolls_sideways', () => {
    const panel = rule(pageCss, '.settings-page__step')
    expect(panel).toContain('background: var(--color-paper-white)')
    expect(panel).toContain('border: var(--border-hairline) solid var(--color-hairline)')
    expect(panel).toContain('border-radius: var(--radius-panel)')
    expect(panel).toContain('min-width: 0')
    expect(panel).toContain('overflow-wrap: anywhere')
    expect(panel).not.toContain('box-shadow')
    expect(rule(pageCss, '.settings-page__form')).toContain('min-width: 0')
  })

  it('test_fr_d1_fr_d2_buttons_and_fields_are_at_least_44px', () => {
    // Buttons and fields are 48px tall (the control height), above the 44px tap target.
    expect(rule(buttonCss, '.button')).toContain('min-height: var(--control-height)')
    expect(rule(fieldCss, '.field__input')).toContain('min-height: var(--control-height)')
    expect(pageCss).not.toMatch(/(?:^|[\s;{])(?:min-)?height\s*:/)
  })
})
