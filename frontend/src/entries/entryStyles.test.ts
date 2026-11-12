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

function rule(file: string, selector: string): string {
  const css = fs.readFileSync(new URL(file, HERE), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css)
  if (match === null) {
    throw new Error(`no rule for ${selector} in ${file}`)
  }
  return match[1] ?? ''
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
    expect(rule('../components/EntryRow.css', '.entry-row__action:hover')).toContain(
      'background: var(--color-peach-wash)',
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

  it('the writing nudge (#30) keeps the list edges, is a quiet surface and not a control', () => {
    const nudge = rule('../pages/EntriesPage.css', '.entries-page__nudge')
    // The global p rule would stop it at 68ch and add 16px below.
    expect(nudge).toContain('max-width: none')
    expect(nudge).toContain('margin: 0 0 var(--space-24)')
    expect(nudge).toContain('background: var(--color-peach-wash)')
    expect(nudge).toContain('border: var(--border-hairline) solid var(--color-hairline)')
    expect(nudge).toContain('border-radius: var(--radius-message)')
    expect(nudge).toContain('color: var(--color-aubergine-ink)')
    expect(nudge).not.toMatch(/--color-plum|--color-error|--color-peach[;)]|--color-saved-peach|-background|shadow|cursor/)
    expect(fs.readFileSync(new URL('../pages/EntriesPage.css', HERE), 'utf8')).not.toMatch(/entries-page__nudge:/)
  })
})
