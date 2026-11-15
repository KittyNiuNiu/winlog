import { describe, expect, it } from 'vitest'
import { REASONS, SERVER_TEXTS, validationError } from '../test/serverReasons.ts'
import {
  TOO_MANY_ATTEMPTS_LATER_MESSAGE,
  UNEXPECTED_ERROR_MESSAGE,
  tooManyAttemptsMessage,
  validationMessages,
  type FieldTexts,
  type ValidationMessages,
} from './requestErrors.ts'
import { EMAIL_REJECTED, LOGIN_PASSWORD_REJECTED, NEW_PASSWORD_REJECTED, PASSWORD_MAX_LENGTH } from './validation.ts'

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

// A server validation error on the login and registration forms shows the page's own texts,
// never the server's (#72): one fixed text per named field, and the generic alert above the
// form for another field or none.
describe('validationMessages (FR-A1, FR-A2, #72)', () => {
  const LOGIN_TEXTS: FieldTexts = { email: EMAIL_REJECTED, password: LOGIN_PASSWORD_REJECTED }
  const REGISTER_TEXTS: FieldTexts = { email: EMAIL_REJECTED, password: NEW_PASSWORD_REJECTED }

  /** Every text the mapping gave, joined, to search for server text. */
  function allText(messages: ValidationMessages): string {
    return [messages.email, messages.password, messages.form].filter((text) => text !== null).join('\n')
  }

  it('test_fr_a1_fr_a2_server_field_texts_are_the_design_notes_texts', () => {
    expect(EMAIL_REJECTED).toBe('Enter a valid email address, such as name@example.com.')
    expect(NEW_PASSWORD_REJECTED).toBe("This password can't be used. Choose a different one.")
    expect(LOGIN_PASSWORD_REJECTED).toBe('Check your password. It can have at most 128 characters.')
    // The same limit as the registration rule's "Use at most 128 characters.".
    expect(LOGIN_PASSWORD_REJECTED).toContain(`at most ${PASSWORD_MAX_LENGTH} characters`)
  })

  it.each([
    ['login', LOGIN_TEXTS, REASONS.emailNoPeriod],
    ['registration', REGISTER_TEXTS, REASONS.emailSpecialUse],
    ['registration', REGISTER_TEXTS, REASONS.emailSpace],
  ])('test_fr_a1_fr_a2_server_email_error_on_%s_gets_the_email_text', (_page, texts, reason) => {
    const messages = validationMessages(validationError([{ field: 'email', reason }]), texts)

    expect(messages).toEqual({ email: EMAIL_REJECTED, password: null, form: null })
  })

  it.each([
    ['test_fr_a2_server_password_error_gets_the_login_password_text', LOGIN_TEXTS, REASONS.loginPasswordTooLong],
    ['test_fr_a2_server_password_unicode_error_gets_the_login_password_text', LOGIN_TEXTS, REASONS.loginPasswordUnicode],
  ])('%s', (_name, texts, reason) => {
    const messages = validationMessages(validationError([{ field: 'password', reason }]), texts)

    expect(messages).toEqual({ email: null, password: LOGIN_PASSWORD_REJECTED, form: null })
  })

  it('test_fr_a1_server_password_error_gets_the_registration_password_text', () => {
    const error = validationError([{ field: 'password', reason: REASONS.registerPasswordSurrogate }])

    expect(validationMessages(error, REGISTER_TEXTS)).toEqual({
      email: null,
      password: NEW_PASSWORD_REJECTED,
      form: null,
    })
  })

  it('test_fr_a1_fr_a2_server_email_and_password_errors_each_get_their_text', () => {
    const error = validationError([
      { field: 'password', reason: REASONS.loginPasswordTooLong },
      { field: 'email', reason: REASONS.emailNoPeriod },
    ])

    expect(validationMessages(error, LOGIN_TEXTS)).toEqual({
      email: EMAIL_REJECTED,
      password: LOGIN_PASSWORD_REJECTED,
      form: null,
    })
  })

  it.each([
    ['the body', [{ field: 'body', reason: REASONS.body }]],
    ['an unknown field', [{ field: 'request', reason: 'Invalid JSON.' }]],
    [
      'two other fields',
      [
        { field: 'body', reason: REASONS.body },
        { field: 'request', reason: 'Invalid JSON.' },
      ],
    ],
    ['no field', []],
  ])('test_fr_a1_fr_a2_server_error_for_%s_gets_the_generic_alert_only', (_case, fields) => {
    for (const texts of [LOGIN_TEXTS, REGISTER_TEXTS]) {
      const messages = validationMessages(validationError(fields), texts)

      expect(messages).toEqual({ email: null, password: null, form: UNEXPECTED_ERROR_MESSAGE })
      expect(messages.form).toBe('Something went wrong. Please try again.')
    }
  })

  it('test_fr_a1_fr_a2_server_error_for_another_field_and_email_gets_both', () => {
    const error = validationError([
      { field: 'body', reason: REASONS.body },
      { field: 'email', reason: REASONS.emailNoPeriod },
    ])

    expect(validationMessages(error, REGISTER_TEXTS)).toEqual({
      email: EMAIL_REJECTED,
      password: null,
      form: UNEXPECTED_ERROR_MESSAGE,
    })
  })

  it('test_fr_a1_fr_a2_field_named_twice_gets_one_message', () => {
    const error = validationError([
      { field: 'email', reason: REASONS.emailNoPeriod },
      { field: 'email', reason: REASONS.emailSpace },
      { field: 'password', reason: REASONS.loginPasswordTooLong },
      { field: 'password', reason: REASONS.loginPasswordUnicode },
    ])

    // One string per field, not a list: a field can show only one server message.
    expect(validationMessages(error, LOGIN_TEXTS)).toEqual({
      email: EMAIL_REJECTED,
      password: LOGIN_PASSWORD_REJECTED,
      form: null,
    })
  })

  it('test_fr_a1_fr_a2_output_never_contains_a_reason', () => {
    const answers = [
      ...Object.values(REASONS).map((reason) => [{ field: 'email', reason }]),
      ...Object.values(REASONS).map((reason) => [{ field: 'password', reason }]),
      ...Object.values(REASONS).map((reason) => [{ field: 'body', reason }]),
      Object.values(REASONS).flatMap((reason) => [
        { field: 'email', reason },
        { field: 'password', reason },
        { field: 'body', reason },
      ]),
    ]
    for (const fields of answers) {
      for (const texts of [LOGIN_TEXTS, REGISTER_TEXTS]) {
        const text = allText(validationMessages(validationError(fields), texts))
        for (const serverText of SERVER_TEXTS) {
          expect(text).not.toContain(serverText)
        }
      }
    }
  })
})
