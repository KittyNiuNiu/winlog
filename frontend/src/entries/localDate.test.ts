import { afterEach, describe, expect, it, vi } from 'vitest'
import { daysBefore, hasDateInLastSevenDays, isCompleteDate, localToday } from './localDate.ts'

// The tests run in Australia/Sydney (vite.config.ts), UTC+11 in November.

afterEach(() => {
  vi.useRealTimers()
})

describe('local today (FR-E2, #2)', () => {
  it('test_fr_e2_date_defaults_to_local_today_not_utc', () => {
    // 08:00 on 2 November in Sydney, still 1 November in UTC.
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-01T21:00:00Z') })

    expect(new Date().toISOString().slice(0, 10)).toBe('2026-11-01')
    expect(localToday()).toBe('2026-11-02')
  })

  it('is worked out when it is called', () => {
    expect(localToday(new Date('2026-11-02T12:59:00Z'))).toBe('2026-11-02')
    expect(localToday(new Date('2026-11-02T13:00:00Z'))).toBe('2026-11-03')
    expect(localToday(new Date('0999-03-04T12:00:00Z'))).toBe('0999-03-04')
  })

  it('a complete date is YYYY-MM-DD; the native input is empty while incomplete', () => {
    expect(isCompleteDate('2026-11-02')).toBe(true)
    expect(isCompleteDate('')).toBe(false)
    expect(isCompleteDate('2026-11')).toBe(false)
  })
})

describe('the last 7 days (FR-N1, #30)', () => {
  it('test_fr_n1_days_before_counts_calendar_dates', () => {
    expect(daysBefore('2026-11-12', 6)).toBe('2026-11-06')
    expect(daysBefore('2026-11-12', 0)).toBe('2026-11-12')
    expect(daysBefore('2026-11-03', 6)).toBe('2026-10-28')
    expect(daysBefore('2027-01-04', 6)).toBe('2026-12-29')
    expect(daysBefore('2028-03-02', 6)).toBe('2028-02-25')
    expect(daysBefore('2028-03-01', 1)).toBe('2028-02-29')
    expect(daysBefore('0099-01-03', 6)).toBe('0098-12-28')
  })

  it('test_fr_n1_days_before_is_not_shifted_by_a_daylight_saving_change', () => {
    // Sydney summer time starts on 4 October 2026 and ends on 5 April 2026.
    expect(daysBefore('2026-10-08', 6)).toBe('2026-10-02')
    expect(daysBefore('2026-04-08', 6)).toBe('2026-04-02')
  })

  it('test_fr_n1_range_is_today_and_the_6_days_before', () => {
    const today = '2026-11-12'
    expect(hasDateInLastSevenDays(['2026-11-12'], today)).toBe(true)
    expect(hasDateInLastSevenDays(['2026-11-06'], today)).toBe(true)
    expect(hasDateInLastSevenDays(['2026-11-05'], today)).toBe(false)
    expect(hasDateInLastSevenDays(['2026-11-13', '2027-01-05'], today)).toBe(false)
    expect(hasDateInLastSevenDays([], today)).toBe(false)
    expect(hasDateInLastSevenDays(['2027-01-05', '2026-11-09', '2025-11-20'], today)).toBe(true)
  })
})
