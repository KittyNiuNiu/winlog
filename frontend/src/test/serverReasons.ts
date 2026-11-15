import { expect } from 'vitest'
import { ValidationError, type FieldError } from '../api/index.ts'

// The backend's own texts for a 422 `validation_failed` from `register` or `login`, exactly
// as its `Registration` and `Credentials` models print them (issue #72, Constraints →
// "Backend reasons"; pydantic 2.14.2 and email-validator 2.3.0 from backend/uv.lock). The
// login and registration forms never show any of them.

/** The `message` of every 422 `validation_failed` (backend/app/errors.py). */
export const VALIDATION_FAILED_MESSAGE = 'The request has invalid fields.'

export const REASONS = {
  emailNoPeriod:
    'value is not a valid email address: The part after the @-sign is not valid. It should have a period.',
  emailSpecialUse:
    'value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.',
  emailSpace: 'value is not a valid email address: The email address contains invalid characters before the @-sign: SPACE.',
  registerPasswordSurrogate: 'Password contains an invalid character (an unpaired surrogate).',
  loginPasswordTooLong: 'String should have at most 128 characters',
  loginPasswordUnicode: 'Input should be a valid string, unable to parse raw data as a unicode string',
  body: 'Body must be valid JSON in UTF-8.',
} as const

const INVALID_EMAIL = 'value is not a valid email address: '

/**
 * The addresses the forms let through (filled in, with an @) and the backend rejects, each
 * as [a short name for the test, the address, the backend's reason] (#72, section B). Both
 * models give the same reasons.
 */
export const REJECTED_ADDRESSES: readonly (readonly [name: string, address: string, reason: string])[] = [
  ...(
    [
      ['alice@invalid', REASONS.emailNoPeriod],
      ['alice@localhost', REASONS.emailNoPeriod],
      ['alice@example.local', REASONS.emailSpecialUse],
      ['alice@example.test', REASONS.emailSpecialUse],
      ['alice @example.com', REASONS.emailSpace],
      ['alice@exam ple.com', `${INVALID_EMAIL}The part after the @-sign contains invalid characters: SPACE.`],
      ['alice@example..com', `${INVALID_EMAIL}An email address cannot have two periods in a row.`],
      ['.alice@example.com', `${INVALID_EMAIL}An email address cannot start with a period.`],
      ['alice@.com', `${INVALID_EMAIL}An email address cannot have a period immediately after the @-sign.`],
      ['a@b@c.com', `${INVALID_EMAIL}The part after the @-sign contains invalid characters: '@'.`],
      ['@example.com', `${INVALID_EMAIL}There must be something before the @-sign.`],
      ['alice@', `${INVALID_EMAIL}There must be something after the @-sign.`],
    ] as const
  ).map(([address, reason]) => [address, address, reason] as const),
  [
    'alice@ and 250 letters and .com',
    `alice@${'a'.repeat(250)}.com`,
    `${INVALID_EMAIL}The email address is too long after the @-sign (1 character too many).`,
  ],
]

/**
 * Every server text a test answer can carry: each reason and the message, and distinctive
 * parts of them, so a reason shown in part (for example without pydantic's prefix) is found too.
 */
export const SERVER_TEXTS: readonly string[] = [
  VALIDATION_FAILED_MESSAGE,
  ...Object.values(REASONS),
  ...REJECTED_ADDRESSES.map(([, , reason]) => reason),
  ...REJECTED_ADDRESSES.map(([, , reason]) => reason.slice(INVALID_EMAIL.length)),
  'value is not a valid email address',
  '@-sign',
  'special-use',
  'SPACE',
  'surrogate',
  'String should',
  'unicode string',
  'valid JSON',
]

/** A 422 `validation_failed` as the API client throws it. */
export function validationError(fields: FieldError[]): ValidationError {
  return new ValidationError(VALIDATION_FAILED_MESSAGE, 422, fields)
}

/**
 * Fails when any server text is in the page: in its text, visually hidden text included, or
 * in any attribute, such as `aria-label`, `title` or `value`. Checks the whole document.
 */
export function expectNoServerText(): void {
  const found: string[] = []
  const text = document.documentElement.textContent ?? ''
  for (const serverText of SERVER_TEXTS) {
    if (text.includes(serverText)) {
      found.push(`text: ${serverText}`)
    }
  }
  for (const element of document.querySelectorAll('*')) {
    for (const { name, value } of Array.from(element.attributes)) {
      for (const serverText of SERVER_TEXTS.filter((part) => value.includes(part))) {
        found.push(`${element.tagName.toLowerCase()}[${name}]: ${serverText}`)
      }
    }
  }
  expect(found, 'server text in the page').toEqual([])
}
