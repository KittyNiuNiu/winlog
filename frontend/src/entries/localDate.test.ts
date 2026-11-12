import { afterEach, describe, expect, it, vi } from 'vitest'
import { isCompleteDate, localToday } from './localDate.ts'

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
