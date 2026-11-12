import { describe, expect, it } from 'vitest'
import {
  NO_FILTER,
  entryQuery,
  filterSearchParams,
  filtersInUse,
  isDate,
  parseFilter,
  startAfterEnd,
  toggleCategory,
} from './reviewFilter.ts'

function parse(query: string) {
  return parseFilter(new URLSearchParams(query))
}

describe('the review filter (FR-R1)', () => {
  it.each(['2026-01-01', '2026-12-31', '2028-02-29', '2000-02-29', '0001-01-01', '2099-06-30'])(
    'test_fr_r1_%s_is_a_real_date',
    (value) => {
      expect(isDate(value)).toBe(true)
    },
  )

  it.each([
    '2026-02-30',
    '2026-02-29',
    '1900-02-29',
    '2026-13-01',
    '2026-00-10',
    '2026-04-31',
    '0000-01-01',
    'abc',
    '',
    '2026-1-1',
    '2026-01-01T00:00',
    ' 2026-01-01',
  ])(
    'test_fr_r1_%s_is_not_a_real_date',
    (value) => {
      expect(isDate(value)).toBe(false)
    },
  )

  it('test_fr_r1_reads_every_filter_from_the_url', () => {
    expect(parse('start_date=2026-01-01&end_date=2026-06-30&category=Learning&category=Achievement&tag=python')).toEqual(
      { startDate: '2026-01-01', endDate: '2026-06-30', categories: ['Achievement', 'Learning'], tags: ['python'] },
    )
  })

  it('test_fr_r1_ignores_values_the_page_cannot_use', () => {
    expect(parse('start_date=2026-02-30&end_date=abc&category=Wins&category=achievement&tag=&tag=%20%20&from=x')).toEqual(
      NO_FILTER,
    )
  })

  it('test_fr_r1_url_tags_are_trimmed_and_used_once_ignoring_case', () => {
    expect(parse('tag=%20Python%20&tag=python&tag=PYTHON&tag=Go&tag=go%20')).toEqual({
      ...NO_FILTER,
      tags: ['Python', 'Go'],
    })
  })

  it('test_fr_r1_url_category_given_twice_is_used_once', () => {
    expect(parse('category=Feedback&category=Feedback').categories).toEqual(['Feedback'])
  })

  it('test_fr_r1_no_filter_writes_an_empty_query', () => {
    expect(filterSearchParams(NO_FILTER).toString()).toBe('')
    expect(entryQuery(NO_FILTER)).toEqual({})
  })

  it('test_fr_r1_writes_the_filters_with_the_api_names', () => {
    const filter = parse('start_date=2026-01-01&end_date=2026-06-30&category=Achievement&category=Learning&tag=python')
    expect(filterSearchParams(filter).toString()).toBe(
      'start_date=2026-01-01&end_date=2026-06-30&category=Achievement&category=Learning&tag=python',
    )
    expect(entryQuery(filter)).toEqual({
      start_date: '2026-01-01',
      end_date: '2026-06-30',
      category: ['Achievement', 'Learning'],
      tag: ['python'],
    })
  })

  it('test_fr_r1_filters_not_in_use_are_left_out_of_the_query', () => {
    expect(entryQuery({ ...NO_FILTER, endDate: '2026-06-30' })).toEqual({ end_date: '2026-06-30' })
    expect(Object.keys(entryQuery({ ...NO_FILTER, tags: ['go'] }))).toEqual(['tag'])
  })

  it('test_fr_r1_query_never_has_an_empty_tag', () => {
    expect(entryQuery({ ...NO_FILTER, tags: ['', '  '] })).toEqual({})
    expect(entryQuery({ ...NO_FILTER, tags: [' go ', ''] })).toEqual({ tag: ['go'] })
  })

  it('test_fr_r1_counts_each_date_category_and_tag_in_use', () => {
    expect(filtersInUse(NO_FILTER)).toBe(0)
    expect(filtersInUse(parse('start_date=2026-01-01&category=Learning&category=Feedback&tag=a&tag=b'))).toBe(5)
    expect(filtersInUse(parse('start_date=2026-02-30'))).toBe(0)
  })

  it('test_fr_r1_start_after_end_only_when_both_are_set', () => {
    expect(startAfterEnd(parse('start_date=2026-06-02&end_date=2026-06-01'))).toBe(true)
    expect(startAfterEnd(parse('start_date=2026-06-01&end_date=2026-06-01'))).toBe(false)
    expect(startAfterEnd(parse('start_date=2027-01-01'))).toBe(false)
    expect(startAfterEnd(parse('end_date=2020-01-01'))).toBe(false)
  })

  it('test_fr_r1_toggling_keeps_the_fixed_category_order', () => {
    expect(toggleCategory(['Feedback'], 'Achievement')).toEqual(['Achievement', 'Feedback'])
    expect(toggleCategory(['Achievement', 'Feedback'], 'Achievement')).toEqual(['Feedback'])
  })
})
