// Checks the login and registration forms run before they send a request. The password
// rule is the backend's rule from #6 (backend/app/passwords.py, openapi.yaml Registration);
// the backend stays the authority and its validation errors are shown too.

export const PASSWORD_MIN_LENGTH = 10
export const PASSWORD_MAX_LENGTH = 128

export const PASSWORD_HINT = 'At least 10 characters, including an uppercase letter, a number and a special character.'

/** One requirement of the password rule that a password breaks. */
export type PasswordProblem = 'too_short' | 'too_long' | 'no_uppercase' | 'no_digit' | 'no_special'

export const PASSWORD_MESSAGES: Record<PasswordProblem, string> = {
  too_short: `Use at least ${PASSWORD_MIN_LENGTH} characters.`,
  too_long: `Use at most ${PASSWORD_MAX_LENGTH} characters.`,
  no_uppercase: 'Add an uppercase letter.',
  no_digit: 'Add a number (0–9).',
  no_special: 'Add a special character, such as ! # - or a space.',
}

const UPPERCASE_LETTER = /^\p{Lu}$/u
const LETTER = /^\p{L}$/u
const DIGIT = /^[0-9]$/

/**
 * The requirements the password breaks, in the backend's order. Like the backend, it
 * counts characters (code points, not UTF-16 units) and checks the password exactly as
 * typed. Uppercase letter: Unicode category Lu. Digit: 0–9 only. Special character:
 * anything that is neither a letter (category L) nor 0–9.
 */
export function passwordProblems(password: string): PasswordProblem[] {
  const characters = Array.from(password)
  const problems: PasswordProblem[] = []
  if (characters.length < PASSWORD_MIN_LENGTH) {
    problems.push('too_short')
  }
  if (characters.length > PASSWORD_MAX_LENGTH) {
    problems.push('too_long')
  }
  if (!characters.some((character) => UPPERCASE_LETTER.test(character))) {
    problems.push('no_uppercase')
  }
  if (!characters.some((character) => DIGIT.test(character))) {
    problems.push('no_digit')
  }
  if (!characters.some((character) => !LETTER.test(character) && !DIGIT.test(character))) {
    problems.push('no_special')
  }
  return problems
}

export const EMAIL_MISSING = 'Enter your email address.'
export const EMAIL_WITHOUT_AT = 'Enter an email address with an @, such as name@example.com.'

/** The email field's message, or null. The server checks the full address. */
export function emailProblem(email: string): string | null {
  const trimmed = email.trim()
  if (trimmed === '') {
    return EMAIL_MISSING
  }
  if (!trimmed.includes('@')) {
    return EMAIL_WITHOUT_AT
  }
  return null
}

export const PASSWORD_MISSING = 'Enter your password.'
