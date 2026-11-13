import { describe, expect, it } from 'vitest'
import { TOO_MANY_ATTEMPTS_LATER_MESSAGE, tooManyAttemptsMessage } from './requestErrors.ts'

// The one text for too many login, demo-login or deletion attempts (FR-A4, design note on #46).

describe('tooManyAttemptsMessage (FR-A4)', () => {
  it.each([
    [900, 'Too many attempts. Please try again in 15 minutes.'],
    [899, 'Too many attempts. Please try again in 15 minutes.'],
    [3600, 'Too many attempts. Please try again in 60 minutes.'],
    [121, 'Too many attempts. Please try again in 3 minutes.'],
    [120, 'Too many attempts. Please try again in 2 minutes.'],
    [61, 'Too many attempts. Please try again in 2 minutes.'],
  ])('test_fr_a4_%i_seconds_round_up_to_whole_minutes', (seconds, message) => {
    expect(tooManyAttemptsMessage(seconds)).toBe(message)
  })

  it.each([60, 59, 30, 1, 0])('test_fr_a4_%i_seconds_say_1_minute_in_the_singular', (seconds) => {
    expect(tooManyAttemptsMessage(seconds)).toBe('Too many attempts. Please try again in 1 minute.')
  })

  it('test_fr_a4_unreadable_retry_after_asks_to_try_again_later', () => {
    expect(tooManyAttemptsMessage(null)).toBe('Too many attempts. Please try again later.')
    expect(TOO_MANY_ATTEMPTS_LATER_MESSAGE).toBe('Too many attempts. Please try again later.')
  })
})
