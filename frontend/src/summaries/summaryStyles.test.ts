// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Checks on the summaries pages' stylesheets that jsdom cannot measure (#33 and its design
// note): row and button sizes, the flat rows, the two-line preview, the column width, and
// that nothing pushes the page sideways at 360px. node:fs is loaded by name because the
// app's TypeScript setup has no Node types.

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
  let depth = 0
  for (let index = block.indexOf('{', start); index < block.length; index += 1) {
    if (block[index] === '{') {
      depth += 1
    } else if (block[index] === '}') {
      depth -= 1
      if (depth === 0) {
        return block.slice(block.indexOf('{', start) + 1, index)
      }
    }
  }
  throw new Error(`unclosed media block for ${width}`)
}

const listCss = css('../pages/SummariesPage.css')
const pageCss = css('../pages/SummaryPage.css')
const buttonCss = css('../components/Button.css')

describe('summaries list styles (#33)', () => {
  it('test_fr_r4_row_is_a_flat_link_at_least_44px_with_the_64px_date_column', () => {
    const row = rule(listCss, '.summary-row')
    expect(row).toContain('grid-template-columns: 64px minmax(0, 1fr)')
    expect(row).toContain('min-height: var(--tap-target)')
    expect(row).toContain('border-top: var(--border-hairline) solid var(--color-hairline)')
    expect(row).not.toContain('box-shadow')
    expect(row).not.toContain('background')
    // The global link style stays off the row.
    expect(row).toContain('color: inherit')
    expect(row).toContain('text-decoration: none')
    expect(rule(listCss, '.summaries-page__list')).toContain('list-style: none')
  })

  it('test_fr_r4_the_year_sits_on_its_own_line', () => {
    expect(rule(listCss, '.summary-row__year')).toContain('display: block')
  })

  it('test_fr_r4_preview_is_cut_to_two_lines', () => {
    const preview = rule(listCss, '.summary-row__preview')
    expect(preview).toContain('-webkit-line-clamp: 2')
    expect(preview).toContain('-webkit-box-orient: vertical')
    expect(preview).toContain('overflow: hidden')
  })

  it('test_fr_r4_nothing_in_the_list_scrolls_sideways_at_360px', () => {
    expect(rule(listCss, '.summaries-page')).toContain('min-width: 0')
    expect(rule(listCss, '.summary-row__body')).toContain('min-width: 0')
    expect(rule(listCss, '.summary-row__filter')).toContain('overflow-wrap: anywhere')
    expect(rule(listCss, '.summary-row__preview')).toContain('overflow-wrap: anywhere')
  })

  it('test_fr_r4_only_the_filter_line_reacts_to_a_hover', () => {
    expect(rule(listCss, '.summary-row:hover .summary-row__filter')).toContain('color: var(--color-plum)')
  })
})

describe('summary page styles (#33)', () => {
  it('test_fr_r5_page_is_one_column_at_most_68ch_that_wraps_long_words', () => {
    const page = rule(pageCss, '.summary-page')
    expect(page).toContain('max-width: var(--measure)')
    expect(page).toContain('min-width: 0')
    expect(page).toContain('overflow-wrap: anywhere')
    expect(rule(pageCss, '.summary-page__source')).toContain('overflow-wrap: anywhere')
  })

  it('test_fr_r5_text_field_is_16rem_on_the_phone_and_22rem_from_48rem', () => {
    const area = rule(pageCss, '.summary-page__field .field__input--area')
    expect(area).toContain('min-height: 16rem')
    expect(area).toContain('resize: vertical')
    expect(rule(media(pageCss, '48rem'), '.summary-page__field .field__input--area')).toContain('min-height: 22rem')
  })

  it('test_fr_r5_phone_actions_save_full_width_then_copy_and_delete_side_by_side', () => {
    const actions = rule(pageCss, '.summary-page__actions')
    expect(actions).toContain('display: grid')
    expect(actions).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))')
    expect(rule(pageCss, '.summary-page__save')).toContain('grid-column: 1 / -1')
    expect(rule(pageCss, '.summary-page__actions .button')).toContain('width: 100%')
  })

  it('test_fr_r5_laptop_actions_in_one_row_with_delete_at_the_right_end', () => {
    const laptop = media(pageCss, '48rem')
    expect(rule(laptop, '.summary-page__actions')).toContain('display: flex')
    expect(rule(laptop, '.summary-page__delete')).toContain('margin-left: auto')
  })

  it('test_fr_r5_back_link_and_buttons_are_at_least_44px', () => {
    expect(rule(pageCss, '.summary-page__back')).toContain('min-height: var(--tap-target)')
    // Buttons are 48px tall (the control height).
    expect(rule(buttonCss, '.button')).toContain('min-height: var(--control-height)')
  })
})
