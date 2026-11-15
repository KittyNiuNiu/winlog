import { describe, expect, it } from 'vitest'
import {
  ENTRY_TEXT_MAX_CHARACTERS,
  RESULT_MAX_CHARACTERS,
  SUMMARY_TEXT_MAX_CHARACTERS,
  TAGS_PER_ENTRY_MAX,
  TAGS_PER_FILTER_MAX,
  TAG_NAME_MAX_CHARACTERS,
  characterCount,
  characterCounter,
  formatCount,
  overLimit,
} from './inputLimits.ts'

// The maximum input sizes (#43): the field limits of openapi.yaml, counted in Unicode
// characters as the backend counts them.

// The contract, read with Node's fs because Vite serves only files inside frontend/ (npm test
// runs there), as in api/client.test.ts.
const nodeFs: { readFileSync(path: string, encoding: 'utf8'): string } = await import(/* @vite-ignore */ `node:${'fs'}`)
const nodeProcess = (globalThis as unknown as { process: { cwd(): string } }).process
const openapiLines = nodeFs.readFileSync(`${nodeProcess.cwd()}/../openapi.yaml`, 'utf8').split('\n')

/**
 * The first `maxItems` in openapi.yaml after the lines that match `markers`, one after the
 * other: for example the `SummaryFilter:` schema, then its `tags:` property.
 */
function contractMaxItems(...markers: RegExp[]): number {
  let index = 0
  for (const marker of markers) {
    index = openapiLines.findIndex((line, at) => at >= index && marker.test(line))
    expect(index, String(marker)).toBeGreaterThanOrEqual(0)
  }
  const line = openapiLines.slice(index).find((each) => /^\s+maxItems: \d+$/.test(each))
  return Number(line?.trim().slice('maxItems: '.length))
}

describe('the limits (FR-E2, FR-R5)', () => {
  it('test_fr_e2_limits_are_the_contract_values', () => {
    expect(ENTRY_TEXT_MAX_CHARACTERS).toBe(2000)
    expect(RESULT_MAX_CHARACTERS).toBe(500)
    expect(TAG_NAME_MAX_CHARACTERS).toBe(40)
    expect(TAGS_PER_ENTRY_MAX).toBe(10)
    expect(SUMMARY_TEXT_MAX_CHARACTERS).toBe(10000)
  })

  it('test_fr_r1_filter_tag_limit_is_the_contract_value', () => {
    expect(TAGS_PER_FILTER_MAX).toBe(20)
    expect(contractMaxItems(/^ {4}SummaryFilter:$/, /^ {8}tags:$/)).toBe(TAGS_PER_FILTER_MAX)
    expect(contractMaxItems(/^ {6}operationId: listEntries$/, /^ {8}- name: tag$/)).toBe(TAGS_PER_FILTER_MAX)
  })

  it('test_fr_e2_characters_are_code_points_not_utf16_units', () => {
    expect(characterCount('')).toBe(0)
    expect(characterCount('abc')).toBe(3)
    expect(characterCount('🎉')).toBe(1)
    expect('🎉'.length).toBe(2)
    expect(characterCount('a\nb')).toBe(3)
    expect(characterCount('Größe 日本語')).toBe(9)
    expect(characterCount('🎉'.repeat(2000))).toBe(2000)
  })

  it('test_fr_e2_a_value_at_the_limit_is_within_it_and_one_more_is_over', () => {
    expect(overLimit('a'.repeat(2000), 2000)).toBe(false)
    expect(overLimit('🎉'.repeat(2000), 2000)).toBe(false)
    expect(overLimit('a'.repeat(2001), 2000)).toBe(true)
    expect(overLimit('🎉'.repeat(2001), 2000)).toBe(true)
  })

  it('test_fr_e2_counts_use_english_format_whatever_the_locale', () => {
    expect(formatCount(1600)).toBe('1,600')
    expect(formatCount(10512)).toBe('10,512')
    expect(formatCount(400)).toBe('400')
  })
})

describe('the counter (FR-E2, FR-R5)', () => {
  it('test_fr_e2_no_counter_below_80_percent', () => {
    expect(characterCounter('a'.repeat(1599), 2000)).toBeNull()
    expect(characterCounter('a'.repeat(399), 500)).toBeNull()
    expect(characterCounter('a'.repeat(7999), 10000)).toBeNull()
  })

  it('test_fr_e2_counter_from_80_percent', () => {
    expect(characterCounter('a'.repeat(1600), 2000)).toEqual({
      visible: '1,600 / 2,000',
      spoken: '1,600 of 2,000 characters',
      over: false,
    })
    expect(characterCounter('a'.repeat(400), 500)?.visible).toBe('400 / 500')
    expect(characterCounter('a'.repeat(8000), 10000)?.visible).toBe('8,000 / 10,000')
  })

  it('test_fr_e2_emoji_at_the_limit_is_not_over', () => {
    expect(characterCounter('🎉'.repeat(2000), 2000)).toEqual({
      visible: '2,000 / 2,000',
      spoken: '2,000 of 2,000 characters',
      over: false,
    })
  })

  it('test_fr_e2_counter_over_the_limit', () => {
    expect(characterCounter('a'.repeat(2105), 2000)).toEqual({
      visible: '2,105 / 2,000',
      spoken: '2,105 of 2,000 characters',
      over: true,
    })
  })
})
