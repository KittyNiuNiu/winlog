import { render } from '@testing-library/react'
import type { ComponentType } from 'react'
import { describe, expect, it } from 'vitest'
import { EntriesIllustration, LoginIllustration, ReviewIllustration } from './Illustrations.tsx'

// The three illustrations (#77, product-spec.md §9 Design, DESIGN.md "Colour blocks and
// illustrations"): flat decorative SVG, colours only through the token classes. The
// checks on the source files are in illustrationSources.test.ts.

const DRAWINGS: [string, ComponentType][] = [
  ['LoginIllustration', LoginIllustration],
  ['EntriesIllustration', EntriesIllustration],
  ['ReviewIllustration', ReviewIllustration],
]

// Every class a shape may have; each sets its colour from a token in Illustrations.css.
const COLOUR_CLASSES = new Set([
  'illustration__backdrop',
  'illustration__line',
  'illustration__shape',
  'illustration__shape--lilac',
  'illustration__shape--apricot',
  'illustration__shape--sage',
  'illustration__shape--rose',
  'illustration__accent',
  'illustration__dot--achievement',
  'illustration__dot--learning',
  'illustration__dot--feedback',
  'illustration__dot--side-project',
  'illustration__handle',
])

const SHAPES = ['circle', 'line', 'rect', 'polygon', 'path']

function svgOf(Drawing: ComponentType): SVGSVGElement {
  const { container } = render(<Drawing />)
  const svgs = container.querySelectorAll('svg')
  expect(svgs).toHaveLength(1)
  expect(container.children).toHaveLength(1)
  return svgs[0]
}

describe('the three illustrations (§9 Design)', () => {
  it.each(DRAWINGS)('test_design_%s_is_one_decorative_svg', (_name, Drawing) => {
    const svg = svgOf(Drawing)

    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('focusable')).toBe('false')
    expect(svg.getAttribute('viewBox')).toBe('0 0 200 160')
    for (const attribute of ['role', 'tabindex', 'aria-label', 'width', 'height', 'style']) {
      expect(svg.hasAttribute(attribute), attribute).toBe(false)
    }
    expect(svg.querySelectorAll('a, button, [tabindex], [onclick]')).toHaveLength(0)
  })

  it.each(DRAWINGS)('test_design_%s_has_no_text_image_gradient_or_filter', (_name, Drawing) => {
    const svg = svgOf(Drawing)

    const forbidden = [
      'text',
      'tspan',
      'title',
      'desc',
      'image',
      'foreignObject',
      'linearGradient',
      'radialGradient',
      'pattern',
      'filter',
      'mask',
      'animate',
      'animateTransform',
      'animateMotion',
      'set',
    ]
    for (const tag of forbidden) {
      expect(svg.getElementsByTagName(tag), tag).toHaveLength(0)
    }
    expect(svg.textContent).toBe('')
    for (const element of svg.querySelectorAll('*')) {
      expect(['g', ...SHAPES], element.tagName).toContain(element.tagName)
    }
  })

  it.each(DRAWINGS)('test_design_%s_takes_every_colour_from_a_token_class', (_name, Drawing) => {
    const svg = svgOf(Drawing)

    const shapes = svg.querySelectorAll(SHAPES.join(','))
    expect(shapes.length).toBeGreaterThan(5)
    for (const shape of shapes) {
      for (const attribute of ['fill', 'stroke', 'style', 'opacity', 'filter']) {
        expect(shape.hasAttribute(attribute), `${shape.tagName} ${attribute}`).toBe(false)
      }
      const classes = Array.from(shape.classList)
      expect(classes.length, shape.outerHTML).toBeGreaterThan(0)
      for (const name of classes) {
        expect(COLOUR_CLASSES.has(name), name).toBe(true)
      }
    }
  })

  it.each(DRAWINGS)('test_design_%s_fills_plum_only_in_small_accents', (_name, Drawing) => {
    const svg = svgOf(Drawing)

    // jsdom has no layout, so the size comes from the points: at full size (200×160) one
    // viewBox unit is one pixel. The pencil lead is 5×5 and the star 15.2×14.5.
    for (const accent of svg.querySelectorAll('.illustration__accent')) {
      expect(accent.tagName).toBe('polygon')
      const points = (accent.getAttribute('points') ?? '').split(' ').map((pair) => pair.split(',').map(Number))
      const xs = points.map(([x]) => x)
      const ys = points.map(([, y]) => y)
      expect(Math.max(...xs) - Math.min(...xs)).toBeLessThanOrEqual(16)
      expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(16)
    }
  })

  it('test_design_the_three_drawings_share_the_backdrop_ground_line_and_sizes', () => {
    const svgs = DRAWINGS.map(([, Drawing]) => svgOf(Drawing))

    expect(svgs.map((svg) => svg.getAttribute('class'))).toEqual([
      'illustration illustration--login',
      'illustration illustration--entries',
      'illustration illustration--review',
    ])
    for (const svg of svgs) {
      const backdrop = svg.querySelector('.illustration__backdrop') as SVGElement
      expect([backdrop.getAttribute('cx'), backdrop.getAttribute('cy'), backdrop.getAttribute('r')]).toEqual([
        '100',
        '82',
        '64',
      ])
      expect(svg.querySelector('line.illustration__line')?.getAttribute('y1')).toBe('148')
    }
  })
})
