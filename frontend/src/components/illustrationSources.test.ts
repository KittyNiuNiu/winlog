// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Source checks for the three illustrations (#77, product-spec.md §9 Design). The files are
// read from disk, as in design.test.ts: Vitest empties every stylesheet it imports, and
// node:fs is loaded by name because the app's TypeScript setup has no Node types.

interface NodeFs {
  readFileSync(path: URL, encoding: 'utf8'): string
  readdirSync(path: URL, options: { recursive: true; encoding: 'utf8' }): string[]
}

const fs = (await import(/* @vite-ignore */ `node:${'fs'}`)) as NodeFs
const SRC = new URL('../', import.meta.url)

describe('the illustration sources (§9 Design)', () => {
  it('test_design_illustration_css_has_the_sizes_and_no_animation', () => {
    const css = fs.readFileSync(new URL('components/Illustrations.css', SRC), 'utf8')

    expect(css).not.toMatch(/animation|transition|gradient|filter|shadow|opacity/)
    expect(css).toMatch(/\.illustration--login\s*\{\s*width:\s*120px;/)
    expect(css).toMatch(/\.illustration--entries,\s*\.illustration--review\s*\{\s*width:\s*160px;/)
    expect(css).toMatch(/aspect-ratio:\s*5 \/ 4/)
    expect(css).toMatch(/max-width:\s*100%/)
    // Every fill and stroke is a token: plum, peach, or a category tint.
    for (const match of css.matchAll(/(?:fill|stroke)\s*:\s*([^;]+);/g)) {
      expect(match[1]).toMatch(
        /^(none|var\(--color-(plum|peach|(achievement|learning|feedback|side-project)-(background|text|dot))\))$/,
      )
    }
  })

  it('test_design_illustrations_are_imported_only_by_the_four_pages_and_the_preview', () => {
    const importers = fs
      .readdirSync(SRC, { recursive: true, encoding: 'utf8' })
      .map((path) => path.split('\\').join('/'))
      .filter((path) => /\.(ts|tsx)$/.test(path) && !/\.test\.tsx?$/.test(path))
      .filter((path) => /from '[^']*\/Illustrations(\.tsx)?'/.test(fs.readFileSync(new URL(path, SRC), 'utf8')))
      .sort()

    expect(importers).toEqual([
      'pages/EntriesPage.tsx',
      'pages/LoginPage.tsx',
      'pages/RegisterPage.tsx',
      'pages/ReviewPage.tsx',
      'pages/dev/ComponentPreviewPage.tsx',
    ])
  })
})
