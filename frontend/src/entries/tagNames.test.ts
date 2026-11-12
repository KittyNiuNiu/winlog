import { describe, expect, it } from 'vitest'
import { addTagNames, matchingTags, mergeKnownTags } from './tagNames.ts'

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
