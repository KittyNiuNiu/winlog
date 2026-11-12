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
})
