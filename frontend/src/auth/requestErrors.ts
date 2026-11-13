// The texts the login and registration forms show for errors that no field explains, and
// the notices the login page shows above its form.
import { NetworkError, type ValidationError } from '../api/index.ts'

export const NETWORK_ERROR_MESSAGE = "Can't reach Winlog. Check your connection and try again."
export const UNEXPECTED_ERROR_MESSAGE = 'Something went wrong. Please try again.'
export const WRONG_CREDENTIALS_MESSAGE = 'Wrong email or password.'
export const ACCOUNT_CREATED_MESSAGE = 'Account created. Please log in.'
export const ACCOUNT_DELETED_MESSAGE = 'Your account has been deleted.'
export const WAKING_UP_MESSAGE = 'The server is waking up. This can take up to a minute.'

/** After this long, a running request shows the waking-up hint (product-spec.md §12). */
export const WAKING_UP_AFTER_MS = 10_000

/** The form-level message for a network error or any other unexpected error. */
export function unexpectedErrorMessage(error: unknown): string {
  return error instanceof NetworkError ? NETWORK_ERROR_MESSAGE : UNEXPECTED_ERROR_MESSAGE
}

/** A server validation error, split into the messages for each form field and the rest. */
export interface ValidationMessages {
  email: string[]
  password: string[]
  /** For errors that name no field on the form, or null. */
  form: string | null
}

export function validationMessages(error: ValidationError): ValidationMessages {
  const messages: ValidationMessages = { email: [], password: [], form: null }
  const other: string[] = []
  for (const { field, reason } of error.fields) {
    if (field === 'email' || field === 'password') {
      messages[field].push(reason)
    } else {
      other.push(reason)
    }
  }
  if (other.length > 0) {
    messages.form = other.join(' ')
  } else if (error.fields.length === 0) {
    messages.form = UNEXPECTED_ERROR_MESSAGE
  }
  return messages
}
