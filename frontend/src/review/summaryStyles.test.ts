// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Checks on the summary panel's stylesheets that jsdom cannot measure (#32 and its design
// note): where the panel sits at each width, that it stays in view on wide windows, and
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

const panelCss = css('./SummaryPanel.css')
const pageCss = css('../pages/ReviewPage.css')

describe('summary panel styles (#32)', () => {
  it('test_fr_r3_panel_is_a_flat_white_panel_40px_below_the_results', () => {
    const panel = rule(panelCss, '.summary-panel')
    expect(panel).toContain('margin-top: var(--space-40)')
    expect(panel).toContain('padding: var(--space-20)')
    expect(panel).toContain('background: var(--color-paper-white)')
    expect(panel).toContain('border: var(--border-hairline) solid var(--color-hairline)')
    expect(panel).toContain('border-radius: var(--radius-panel)')
    expect(panel).not.toContain('box-shadow')
  })

  it('test_fr_r3_nothing_in_the_panel_scrolls_sideways_at_360px', () => {
    expect(rule(panelCss, '.summary-panel')).toContain('min-width: 0')
    expect(rule(panelCss, '.summary-panel')).toContain('overflow-wrap: anywhere')
    expect(rule(panelCss, '.summary-panel__source')).toContain('overflow-wrap: anywhere')
    expect(rule(panelCss, '.summary-panel .button')).toContain('width: 100%')
    expect(rule(pageCss, '.review-page__main')).toContain('min-width: 0')
  })

  it('test_fr_r3_text_field_is_at_least_12rem_and_resizes_vertically', () => {
    const area = rule(panelCss, '.summary-panel__field .field__input--area')
    expect(area).toContain('min-height: 12rem')
    expect(area).toContain('resize: vertical')
  })

  it('test_fr_r3_narrow_laptop_windows_keep_the_panel_below_at_most_40rem_wide', () => {
    const panel = rule(media(panelCss, '48rem'), '.summary-panel')
    expect(panel).toContain('max-width: 40rem')
    expect(panel).toContain('padding: var(--space-24)')
  })

  it('test_fr_r3_from_75rem_the_panel_is_a_sticky_column_to_the_right', () => {
    const wide = media(pageCss, '75rem')
    const layout = rule(wide, '.review-page__layout')
    expect(layout).toContain('display: grid')
    expect(layout).toContain('grid-template-columns: minmax(0, 1fr) 22.5rem')
    expect(layout).toContain('column-gap: var(--space-32)')
    expect(layout).toContain('align-items: start')
    const panel = rule(wide, '.review-page__layout > .summary-panel')
    expect(panel).toContain('position: sticky')
    expect(panel).toContain('top: var(--space-24)')
    expect(panel).toContain('max-height: calc(100dvh - 2 * var(--space-24))')
    expect(panel).toContain('overflow-y: auto')
    expect(panel).toContain('max-width: none')
  })
})
