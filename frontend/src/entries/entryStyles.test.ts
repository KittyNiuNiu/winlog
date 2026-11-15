// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Checks on the entry form's stylesheets that jsdom cannot measure: tap targets and long
// words (DESIGN.md → Layout, AGENTS.md: 360px). node:fs is loaded by name because the
// app's TypeScript setup has no Node types.

interface NodeFs {
  readFileSync(path: URL, encoding: 'utf8'): string
}

const fs = (await import(/* @vite-ignore */ `node:${'fs'}`)) as NodeFs
const HERE = new URL('./', import.meta.url)

function source(file: string): string {
  return fs.readFileSync(new URL(file, HERE), 'utf8')
}

function withoutComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** The declarations of the first rule with exactly this selector in a piece of CSS. */
function ruleIn(css: string, selector: string, where: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css)
  if (match === null) {
    throw new Error(`no rule for ${selector} in ${where}`)
  }
  return match[1] ?? ''
}

function rule(file: string, selector: string): string {
  return ruleIn(withoutComments(source(file)), selector, file)
}

/** The rules inside `@media <query> { … }` in a stylesheet, comments removed. */
function mediaBlock(file: string, query: string): string {
  const css = withoutComments(source(file))
  const start = css.indexOf(`@media ${query} {`)
  if (start === -1) {
    throw new Error(`no @media ${query} in ${file}`)
  }
  let depth = 0
  for (let index = css.indexOf('{', start); index < css.length; index += 1) {
    if (css[index] === '{') depth += 1
    if (css[index] === '}') depth -= 1
    if (depth === 0) {
      return css.slice(css.indexOf('{', start) + 1, index)
    }
  }
  throw new Error(`@media ${query} in ${file} is not closed`)
}

describe('entry form styles', () => {
  it('tag chips and their remove buttons are at least 44px', () => {
    expect(rule('TagField.css', '.tag-chip')).toContain('min-height: var(--tap-target)')
    expect(rule('TagField.css', '.tag-chip__remove')).toContain('width: var(--tap-target)')
    expect(rule('TagField.css', '.tag-chip__remove')).toContain('height: var(--tap-target)')
    expect(rule('TagField.css', '.tag-list__option')).toContain('min-height: var(--control-height)')
  })

  it('long tag names wrap inside the chip and in the list, which stays the input width', () => {
    expect(rule('TagField.css', '.tag-chip')).toContain('max-width: 100%')
    expect(rule('TagField.css', '.tag-chip__label')).toContain('overflow-wrap: anywhere')
    expect(rule('TagField.css', '.tag-list__option')).toContain('overflow-wrap: anywhere')
    expect(rule('TagField.css', '.tag-list')).toMatch(/left: 0;[\s\S]*right: 0;/)
  })

  it('the category chips wrap, and Save entry is full width on the phone', () => {
    expect(rule('EntryForm.css', '.entry-form__chips')).toContain('flex-wrap: wrap')
    expect(rule('EntryForm.css', '.entry-form__actions .button')).toContain('width: 100%')
  })

  it('the dialog keeps 20px each side on the phone and has no shadow', () => {
    const dialog = rule('DiscardDialog.css', '.discard-dialog')
    expect(dialog).toContain('width: min(25rem, 100% - 2 * var(--space-20))')
    expect(dialog).not.toContain('box-shadow')
  })

  it('the suggestion actions and marks (#28): 44px targets, dashed marks, marks never wrap', () => {
    expect(rule('EntryForm.css', '.quiet-action')).toContain('min-height: var(--tap-target)')
    expect(rule('EntryForm.css', '.quiet-action')).toContain('min-width: var(--tap-target)')
    expect(rule('EntryForm.css', '.quiet-action')).toContain('background: transparent')
    expect(rule('EntryForm.css', '.quiet-action')).toContain('border: 0')
    expect(rule('EntryForm.css', '.quiet-action')).toContain('max-width: 100%')
    expect(rule('EntryForm.css', '.entry-form__suggest-row')).toContain('flex-wrap: wrap')
    expect(rule('EntryForm.css', '.entry-form__suggest-button')).toContain('max-width: 100%')
    const tag = rule('TagField.css', '.tag-chip--suggested')
    expect(tag).toContain('border-style: dashed')
    expect(tag).toContain('border-color: var(--color-muted-plum-grey)')
    // No tint and no plum fill on a suggested tag.
    expect(tag).not.toContain('background')
    expect(rule('TagField.css', '.tag-chip__mark')).toContain('white-space: nowrap')
    expect(rule('TagField.css', '.tag-chip__mark')).toContain('flex: none')
    expect(rule('../components/CategoryChip.css', '.chip--suggested')).toContain('border-style: dashed')
    expect(rule('../components/CategoryChip.css', '.chip__mark')).toContain('white-space: nowrap')
  })
})

describe('entries page styles (#29)', () => {
  it('the Edit and Delete actions are 44×44, always visible, with no fill until hover', () => {
    const action = rule('../components/EntryRow.css', '.entry-row__action')
    expect(action).toContain('width: var(--tap-target)')
    expect(action).toContain('height: var(--tap-target)')
    expect(action).toContain('background: transparent')
    expect(action).not.toContain('opacity')
    // #90: the shared Secondary hover fill, with a Plum icon. The Peach wash workaround is gone.
    const hover = rule('../components/EntryRow.css', '.entry-row__action:hover')
    expect(hover).toContain('background: var(--color-secondary-hover)')
    expect(hover).toContain('color: var(--color-plum)')
    expect(hover).not.toContain('--color-peach-wash')
    expect(source('../components/EntryRow.css')).not.toMatch(/workaround|equals the page ground/i)
  })

  it('test_fr_e4_from_64rem_edit_and_delete_take_a_fourth_column_on_the_label_line (#90)', () => {
    const block = mediaBlock('../components/EntryRow.css', '(min-width: 64rem)')
    const where = 'EntryRow.css @media (min-width: 64rem)'
    // Only rows with actions change; the 48rem layout stays below 64rem.
    const row = ruleIn(block, '.entry-row--with-actions', where)
    expect(row).toContain('grid-template-columns: 64px 120px minmax(0, 1fr) auto')
    expect(row).toContain("grid-template-areas: 'date category body actions'")
    expect(block).not.toMatch(/(^|[\s}])\.entry-row\s*\{/)
    // The wrapper gives the label and the actions to the grid, so the DOM order stays.
    expect(ruleIn(block, '.entry-row--with-actions .entry-row__category--with-actions', where)).toContain(
      'display: contents',
    )
    // The label keeps its own width: its tint never stretches across the column.
    const label = ruleIn(block, '.entry-row--with-actions .category-label', where)
    expect(label).toContain('grid-area: category')
    expect(label).toContain('justify-self: start')
    // Centred on the label's 26px line, reaching 9px into the padding; the 48rem margin-left goes.
    const actions = ruleIn(block, '.entry-row--with-actions .entry-row__actions', where)
    expect(actions).toContain('grid-area: actions')
    expect(actions).toContain('margin: calc((26px - var(--tap-target)) / 2) 0')
    // The phone's and the 48rem layout are as before.
    expect(rule('../components/EntryRow.css', '.entry-row__actions')).toContain(
      'margin: calc((26px - var(--tap-target)) / 2) 0',
    )
    expect(ruleIn(mediaBlock('../components/EntryRow.css', '(min-width: 48rem)'), '.entry-row__actions', '48rem')).toContain(
      'margin: 0 0 0 calc(-1 * var(--space-12))',
    )
  })

  it('read-only tags wrap, long tag names wrap inside the pill, and there is no tint or plum', () => {
    expect(rule('../components/EntryRow.css', '.entry-row__tags')).toContain('flex-wrap: wrap')
    const tag = rule('../components/EntryRow.css', '.entry-row__tag')
    expect(tag).toContain('max-width: 100%')
    expect(tag).toContain('overflow-wrap: anywhere')
    expect(tag).not.toMatch(/--category-|--color-plum/)
  })

  it('the delete dialog keeps 20px each side on the phone and has no shadow', () => {
    const dialog = rule('DeleteEntryDialog.css', '.delete-dialog')
    expect(dialog).toContain('width: min(25rem, 100% - 2 * var(--space-20))')
    expect(dialog).not.toContain('box-shadow')
  })

  it('the messages and the list share the page column, and "New entry" is full width on the phone', () => {
    expect(rule('../pages/EntriesPage.css', '.entries-page')).not.toContain('max-width')
    expect(rule('../pages/EntriesPage.css', '.entries-page__new .button')).toContain('width: 100%')
  })

  it('test_fr_n1_the_writing_nudge (#30, #90) keeps the list edges, has its own surface and is not a control', () => {
    const nudge = rule('../pages/EntriesPage.css', '.entries-page__nudge')
    // The global p rule would stop it at 68ch and add 16px below.
    expect(nudge).toContain('max-width: none')
    expect(nudge).toContain('margin: 0 0 var(--space-24)')
    // #90: the Nudge fill, the panel radius, 16px by 20px padding and centred, balanced text,
    // so it does not look like the info message (Peach wash) or the saved message.
    expect(nudge).toContain('background: var(--color-nudge-fill)')
    expect(nudge).toContain('border: var(--border-hairline) solid var(--color-hairline)')
    expect(nudge).toContain('border-radius: var(--radius-panel)')
    expect(nudge).toContain('padding: var(--space-16) var(--space-20)')
    expect(nudge).toContain('color: var(--color-aubergine-ink)')
    expect(nudge).toContain('font-size: var(--text-body-size)')
    expect(nudge).toContain('font-weight: 400')
    expect(nudge).toContain('text-align: center')
    expect(nudge).toContain('text-wrap: balance')
    // Not Paper white, which is the info message's Peach wash in dark mode.
    expect(nudge).not.toMatch(/--color-peach-wash|--color-paper-white|--radius-message/)
    expect(nudge).not.toMatch(
      /--color-plum|--color-error|--color-peach[;)]|--color-saved-peach|-background|shadow|cursor|animation|transition/,
    )
    expect(source('../pages/EntriesPage.css')).not.toMatch(/entries-page__nudge:/)
  })
})

describe('maximum input sizes (#43 design note)', () => {
  it('test_fr_e2_counter_8px_under_the_field_messages_4px_under_it_in_the_error_colour_over_the_limit', () => {
    const counter = rule('../components/TextField.css', '.field__counter')
    const over = rule('../components/TextField.css', '.field__counter--over')
    expect(counter).toContain('margin: var(--space-8) 0 0')
    expect(counter).toContain('font-size: var(--text-body-small-size)')
    expect(counter).toContain('color: var(--color-muted-plum-grey)')
    expect(counter).toContain('white-space: nowrap')
    // Spans the field so its end aligns with the field's right edge at 1280px too: without
    // this the global p rule caps it at 68ch, short of a 697px field (design review 1).
    expect(counter).toContain('max-width: none')
    expect(counter).toContain('text-align: end')
    expect(over).not.toMatch(/max-width|width|margin|padding|text-align/)
    expect(over).toContain('color: var(--color-error)')
    expect(over).toContain('font-weight: 600')
    expect(rule('../components/TextField.css', '.field__counter + .field__messages')).toContain(
      'margin-top: var(--space-4)',
    )
  })

  it('test_fr_e2_suggest_hint_is_a_muted_line_8px_under_the_suggest_row', () => {
    const hint = rule('EntryForm.css', '.entry-form__suggest-hint')
    expect(hint).toContain('margin: var(--space-8) 0 0')
    expect(hint).toContain('font-size: var(--text-body-small-size)')
    expect(hint).toContain('color: var(--color-muted-plum-grey)')
  })
})
