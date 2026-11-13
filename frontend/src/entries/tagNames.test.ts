import { describe, expect, it } from 'vitest'
import {
  addTagNames,
  addTagNamesWithin,
  joinTagNames,
  matchingTags,
  mergeKnownTags,
  tagLimitProblems,
} from './tagNames.ts'

describe('tag names (FR-E3)', () => {
  it('test_fr_e3_names_are_trimmed_and_empty_names_skipped', () => {
    expect(addTagNames([], ['  python ', '', '   ', 'go'])).toEqual(['python', 'go'])
  })

  it('test_fr_e3_a_name_already_added_ignoring_case_is_not_added_again', () => {
    expect(addTagNames(['Python'], ['python', 'PYTHON', 'Go', 'go'])).toEqual(['Python', 'Go'])
  })

  it('test_fr_e3_matching_tags_contain_the_typed_text_ignoring_case_without_added_ones', () => {
    const known = ['Leadership', 'pytest', 'Python', 'TypeScript']

    expect(matchingTags(known, [], 'PY')).toEqual(['pytest', 'Python'])
    expect(matchingTags(known, [], 'script')).toEqual(['TypeScript'])
    expect(matchingTags(known, ['python'], 'py')).toEqual(['pytest'])
    expect(matchingTags(known, [], '  ')).toEqual([])
    expect(matchingTags(known, [], ' lead ')).toEqual(['Leadership'])
  })

  it('merges new tags into the known ones, sorted without regard to case', () => {
    expect(mergeKnownTags(['beta', 'Delta'], ['alpha', 'BETA', 'Charlie'])).toEqual(['alpha', 'beta', 'Charlie', 'Delta'])
  })
})

describe('tag limits (#43, FR-E2)', () => {
  const ten = Array.from({ length: 10 }, (_, index) => `Tag ${index}`)

  it('test_fr_e2_names_of_up_to_40_characters_are_added_trimmed', () => {
    const forty = 'a'.repeat(40)
    const emoji = '🎉'.repeat(40)

    expect(addTagNamesWithin([], [`  ${forty}  `, emoji])).toEqual({
      tags: [forty, emoji],
      rejected: [],
      problems: { tooLong: false, tooMany: false },
    })
  })

  it('test_fr_e2_a_name_over_40_characters_is_not_added', () => {
    const long = 'a'.repeat(41)

    expect(addTagNamesWithin(['Go'], [` ${long} `, 'Rust'])).toEqual({
      tags: ['Go', 'Rust'],
      rejected: [long],
      problems: { tooLong: true, tooMany: false },
    })
  })

  it('test_fr_e2_an_11th_tag_is_not_added', () => {
    expect(addTagNamesWithin(ten, ['Eleven', 'tag 0'])).toEqual({
      tags: ten,
      rejected: ['Eleven'],
      problems: { tooLong: false, tooMany: true },
    })
  })

  it('test_fr_e2_pasted_names_are_added_in_order_until_there_are_10', () => {
    const result = addTagNamesWithin(ten.slice(0, 8), ['a', 'b'.repeat(41), 'c', 'd', 'e'])

    expect(result.tags).toEqual([...ten.slice(0, 8), 'a', 'c'])
    expect(result.rejected).toEqual(['b'.repeat(41), 'd', 'e'])
    expect(result.problems).toEqual({ tooLong: true, tooMany: true })
    expect(joinTagNames(result.rejected)).toBe(`${'b'.repeat(41)}, d, e`)
  })

  it('test_fr_e2_tag_limit_problems_while_they_still_apply', () => {
    const long = 'a'.repeat(41)
    expect(tagLimitProblems([], '')).toEqual({ tooLong: false, tooMany: false })
    expect(tagLimitProblems([], long)).toEqual({ tooLong: true, tooMany: false })
    expect(tagLimitProblems([], ` ${'a'.repeat(40)} `)).toEqual({ tooLong: false, tooMany: false })
    expect(tagLimitProblems([long], '')).toEqual({ tooLong: true, tooMany: false })
    expect(tagLimitProblems(ten, '')).toEqual({ tooLong: false, tooMany: false })
    expect(tagLimitProblems(ten, 'x')).toEqual({ tooLong: false, tooMany: true })
    expect(tagLimitProblems(ten, '  ')).toEqual({ tooLong: false, tooMany: false })
    expect(tagLimitProblems([...ten, 'x'], '')).toEqual({ tooLong: false, tooMany: true })
    expect(tagLimitProblems(ten, `x, ${long}`)).toEqual({ tooLong: true, tooMany: true })
  })
})
