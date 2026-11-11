// @vitest-environment node
import { describe, expect, it } from 'vitest'

// Checks of the design rules from DESIGN.md and #75 on the source files: the tokens in
// index.css, colours only from tokens, the old palette gone, and sentence case.
//
// The files are read from disk: Vitest empties every stylesheet it imports, even with
// `?raw`. node:fs is loaded by name because the app's TypeScript setup has no Node types.

interface NodeFs {
  readFileSync(path: URL, encoding: 'utf8'): string
  readdirSync(path: URL, options: { recursive: true; encoding: 'utf8' }): string[]
}

const fs = (await import(/* @vite-ignore */ `node:${'fs'}`)) as NodeFs
const SRC = new URL('./', import.meta.url)

function read(path: string, base: URL = SRC): string {
  return fs.readFileSync(new URL(path, base), 'utf8')
}

/** Every CSS, TS and TSX file under src/, by its path relative to src/ ("./index.css"). */
const sources: Record<string, string> = Object.fromEntries(
  fs
    .readdirSync(SRC, { recursive: true, encoding: 'utf8' })
    .map((path) => path.split('\\').join('/'))
    .filter((path) => /\.(css|ts|tsx)$/.test(path) && !path.endsWith('schema.d.ts'))
    .map((path) => [`./${path}`, read(path)]),
)

const indexCss = sources['./index.css'] ?? ''
const favicon = read('../public/favicon.svg')
const indexHtml = read('../index.html')

function withoutComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** The custom properties set in a block of CSS declarations. */
function tokensIn(block: string): Map<string, string> {
  const tokens = new Map<string, string>()
  for (const match of block.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    tokens.set(match[1], match[2].trim().toLowerCase())
  }
  return tokens
}

const css = withoutComments(indexCss)
const lightBlock = /^:root\s*\{([\s\S]*?)^\}/m.exec(css)?.[1] ?? ''
const darkBlock = /@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([\s\S]*?)\}\s*\}/.exec(css)?.[1] ?? ''
const light = tokensIn(lightBlock)
const darkOverrides = tokensIn(darkBlock)
const dark = new Map([...light, ...darkOverrides])

// DESIGN.md → Colors: [token, light, dark].
const COLORS: [string, string, string][] = [
  ['--color-plum', '#7a2e68', '#e7a3cf'],
  ['--color-on-plum', '#ffffff', '#2a0f23'],
  ['--color-peach', '#f9d9cb', '#3e2433'],
  ['--color-on-peach', '#5e2150', '#f6c2a9'],
  ['--color-saved-peach', '#fce3d6', '#3a2330'],
  ['--color-on-saved-peach', '#5e2150', '#f6c2a9'],
  ['--color-achievement-background', '#fbe0cf', '#3d2618'],
  ['--color-achievement-text', '#7a3412', '#f4be9a'],
  ['--color-achievement-dot', '#c76a3a', '#c76a3a'],
  ['--color-learning-background', '#e8e0f6', '#2d2542'],
  ['--color-learning-text', '#4b3684', '#cdbef0'],
  ['--color-learning-dot', '#7b66b8', '#7b66b8'],
  ['--color-feedback-background', '#f8dce2', '#3f1e29'],
  ['--color-feedback-text', '#8a2440', '#f2afc0'],
  ['--color-feedback-dot', '#c25570', '#c25570'],
  ['--color-side-project-background', '#ddede0', '#1e3326'],
  ['--color-side-project-text', '#2e5a3a', '#a9d7b3'],
  ['--color-side-project-dot', '#5e9468', '#5e9468'],
  ['--color-blush-white', '#fffaf7', '#1a1519'],
  ['--color-peach-wash', '#fff1ea', '#241d23'],
  ['--color-aubergine-ink', '#2a1f2a', '#f3e9ee'],
  ['--color-muted-plum-grey', '#6a5966', '#b9a8b3'],
  ['--color-hairline', '#f0dcd2', '#3a2f38'],
  ['--color-field-border', '#e8d3c9', '#3a2f38'],
  ['--color-error', '#a8253b', '#f4a3b0'],
]

describe('design tokens in index.css', () => {
  it.each(COLORS)('%s is %s in light mode and %s in dark mode', (token, lightValue, darkValue) => {
    expect(light.get(token)).toBe(lightValue)
    expect(dark.get(token)).toBe(darkValue)
  })

  it('paper white is white in light mode and peach wash in dark mode', () => {
    expect(light.get('--color-paper-white')).toBe('#ffffff')
    expect(dark.get('--color-paper-white')).toBe('var(--color-peach-wash)')
  })

  it('category dots have one value for both modes', () => {
    for (const name of ['achievement', 'learning', 'feedback', 'side-project']) {
      expect(darkOverrides.has(`--color-${name}-dot`)).toBe(false)
    }
  })

  it('has the two shadows, with the dark-mode focus glow from the product owner', () => {
    expect(light.get('--shadow-action-lift')).toBe('0 4px 12px rgba(122, 46, 104, 0.25)')
    expect(darkOverrides.has('--shadow-action-lift')).toBe(false)
    expect(light.get('--shadow-focus-glow')).toBe('0 0 0 3px #f6ddeb')
    expect(dark.get('--shadow-focus-glow')).toBe('0 0 0 3px rgba(231, 163, 207, 0.3)')
  })

  it('has the spacing scale, radii, borders and line length', () => {
    for (const size of [4, 8, 12, 16, 20, 24, 32, 40, 48]) {
      expect(light.get(`--space-${size}`)).toBe(`${size}px`)
    }
    expect(light.get('--radius-pill')).toBe('22px')
    expect(light.get('--radius-button')).toBe('14px')
    expect(light.get('--radius-button-large')).toBe('16px')
    expect(light.get('--radius-field')).toBe('14px')
    expect(light.get('--radius-panel')).toBe('14px')
    expect(light.get('--radius-label')).toBe('10px')
    expect(light.get('--radius-message')).toBe('12px')
    expect(light.get('--radius-dialog')).toBe('18px')
    expect(light.get('--border-hairline')).toBe('1px')
    expect(light.get('--border-control')).toBe('1.5px')
    expect(light.get('--measure')).toBe('68ch')
  })

  it('has the type scale (rem at the default 16px text size)', () => {
    const rem = (token: string) => Number(light.get(token)?.replace('rem', '')) * 16
    expect(rem('--text-display-size')).toBe(40)
    expect(rem('--text-headline-size')).toBe(32)
    expect(rem('--text-headline-panel-size')).toBe(26)
    expect(rem('--text-title-size')).toBe(20)
    expect(rem('--text-body-size')).toBe(16)
    expect(rem('--text-label-size')).toBe(15)
    expect(rem('--text-label-small-size')).toBe(13)
    expect(rem('--text-wordmark-size')).toBe(24)
    expect(rem('--text-wordmark-laptop-size')).toBe(30)
    expect(light.get('--text-wordmark-weight')).toBe('800')
    expect(light.get('--text-display-line-height')).toBe('1.05')
    expect(light.get('--text-display-letter-spacing')).toBe('-0.03em')
  })

  it('uses Bricolage Grotesque and Figtree with the DESIGN.md fallbacks', () => {
    expect(light.get('--font-display')).toBe("'bricolage grotesque variable', 'figtree variable', system-ui, sans-serif")
    expect(light.get('--font-body')).toBe("'figtree variable', system-ui, sans-serif")
  })
})

const OLD_PALETTE = ['#1f5f8b', '#8cc4ec', '#e3eef6', '#1d2430', '#556070', '#f4f6f9', '#d9dee6', '#14171c', '#1f2f3d']
const NAMED_COLOURS =
  /(?<![\w-])(white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|brown|navy|teal|maroon|olive|silver|gold|cyan|magenta|lime|indigo|violet|plum|peachpuff|salmon|coral|tomato|crimson)(?![\w-])/i

describe('colours come from tokens', () => {
  const files = Object.entries(sources).filter(([path]) => !path.endsWith('.test.ts') && !path.endsWith('.test.tsx'))

  it('finds the source files', () => {
    expect(files.length).toBeGreaterThan(20)
  })

  it('no CSS or TSX file outside index.css has a colour value', () => {
    const offenders: string[] = []
    for (const [path, source] of files) {
      if (path === './index.css' || !/\.(css|tsx)$/.test(path)) {
        continue
      }
      // Ignore comments and custom property names such as --color-paper-white.
      const code = withoutComments(source).replace(/--[\w-]+/g, '')
      const values = path.endsWith('.css') ? code : (code.match(/style=\{\{[^}]*\}\}/g) ?? []).join('\n')
      if (/#[0-9a-f]{3,8}\b/i.test(code.replace(/href="#\w+"/g, '')) || /\b(rgba?|hsla?)\(/i.test(code)) {
        offenders.push(path)
      } else if (NAMED_COLOURS.test(values)) {
        offenders.push(path)
      }
    }
    expect(offenders).toEqual([])
  })

  it('the old blue palette is gone from src, public and index.html', () => {
    const everything = [...Object.values(sources), favicon, indexHtml].join('\n').toLowerCase()
    for (const colour of OLD_PALETTE) {
      // Only this test file names the old colours, to look for them.
      expect(everything.split(colour).length - 1, colour).toBe(designTestMentions(colour))
    }
  })

  it('the favicon is plum', () => {
    expect(favicon).toContain('fill="#7A2E68"')
  })
})

/** How often this test file itself names a colour (in OLD_PALETTE above). */
function designTestMentions(colour: string): number {
  const self = sources['./design.test.ts'] ?? ''
  return self.toLowerCase().split(colour).length - 1
}

describe('sentence case and fonts', () => {
  it('no stylesheet turns text into capitals', () => {
    for (const [path, source] of Object.entries(sources)) {
      if (path.endsWith('.css')) {
        expect(source, path).not.toMatch(/text-transform\s*:\s*(uppercase|capitalize)/)
      }
    }
  })

  it('fonts are self-hosted: no Google Fonts host anywhere', () => {
    const everything = [...Object.values(sources), indexHtml].join('\n')
    expect(everything.includes('fonts.googleapis' + '.com')).toBe(false)
    expect(everything.includes('fonts.gstatic' + '.com')).toBe(false)
  })
})
