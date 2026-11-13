import type { components } from './schema'

type ErrorBody = components['schemas']['Error']

/** A machine-readable error code from `openapi.yaml`. */
export type ErrorCode = ErrorBody['code']

/** One failing field of a validation error. */
export type FieldError = components['schemas']['FieldError']

/** The daily AI limit that was reached. */
export type LimitName = NonNullable<ErrorBody['limit']>

/**
 * The base class of every error the API client throws. Screens check the subclass with
 * `instanceof` and show their own text; `message` is the server's message, or a short
 * English description for errors the client creates itself.
 */
export abstract class ApiError extends Error {
  /** The HTTP status of the response, or null when there was no response. */
  readonly status: number | null

  constructor(message: string, status: number | null, options?: ErrorOptions) {
    super(message, options)
    this.status = status
  }
}

/** `validation_failed`: a field is missing or invalid. */
export class ValidationError extends ApiError {
  override readonly name = 'ValidationError'
  /** Each failing field and why it failed. */
  readonly fields: FieldError[]

  constructor(message: string, status: number, fields: FieldError[]) {
    super(message, status)
    this.fields = fields
  }
}

/** `not_authenticated`: the token is missing, invalid, expired or revoked. */
export class NotAuthenticatedError extends ApiError {
  override readonly name = 'NotAuthenticatedError'
}

/** `invalid_credentials`: wrong email or password at login. */
export class InvalidCredentialsError extends ApiError {
  override readonly name = 'InvalidCredentialsError'
}

/** `wrong_password`: the current password for account deletion is wrong. */
export class WrongPasswordError extends ApiError {
  override readonly name = 'WrongPasswordError'
}

/** `email_already_registered`: an account with this email already exists. */
export class EmailAlreadyRegisteredError extends ApiError {
  override readonly name = 'EmailAlreadyRegisteredError'
}

/**
 * `not_found`: the entry or summary does not exist or belongs to another user. Demo-login
 * also returns it when the demo is turned off.
 */
export class NotFoundError extends ApiError {
  override readonly name = 'NotFoundError'
}

/** `no_matching_entries`: no entries match the summary filter, so nothing was generated. */
export class NoMatchingEntriesError extends ApiError {
  override readonly name = 'NoMatchingEntriesError'
}

/**
 * `summary_input_too_large`: the matching entries have too much text for one summary, so
 * nothing was generated and nothing counted (#43). The user should narrow the filter.
 */
export class SummaryInputTooLargeError extends ApiError {
  override readonly name = 'SummaryInputTooLargeError'
}

/** `limit_reached`: a daily AI limit is reached. */
export class LimitReachedError extends ApiError {
  override readonly name = 'LimitReachedError'
  /** Which daily limit was reached, or null if the server did not say. */
  readonly limit: LimitName | null

  constructor(message: string, status: number, limit: LimitName | null) {
    super(message, status)
    this.limit = limit
  }
}

/** `ai_unavailable`: the AI provider failed or timed out. Nothing was saved. */
export class AiUnavailableError extends ApiError {
  override readonly name = 'AiUnavailableError'
}

/** `demo_account_not_deletable`: the demo account cannot be deleted (#21). */
export class DemoAccountNotDeletableError extends ApiError {
  override readonly name = 'DemoAccountNotDeletableError'
}

/** The request did not reach the server, or no response came back. */
export class NetworkError extends ApiError {
  override readonly name = 'NetworkError'

  constructor(options?: ErrorOptions) {
    super('The server could not be reached.', null, options)
  }
}

/**
 * Any other unexpected outcome: for example a 500, an error code without its own class
 * (`internal_error`, `database_unreachable`, `method_not_allowed`), a response that is not
 * the contract's JSON, or a missing API base URL.
 */
export class UnknownError extends ApiError {
  override readonly name = 'UnknownError'
  /** The error code from the response, or null when the response had none. */
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null, options?: ErrorOptions) {
    super(message, status, options)
    this.code = code
  }
}

function isErrorBody(body: unknown): body is { code: string; message: string } & Partial<ErrorBody> {
  if (typeof body !== 'object' || body === null) {
    return false
  }
  const { code, message } = body as Record<string, unknown>
  return typeof code === 'string' && typeof message === 'string'
}

const LIMIT_NAMES: readonly string[] = ['user_suggestions', 'user_summaries', 'global'] satisfies LimitName[]

function fieldErrors(fields: unknown): FieldError[] {
  if (!Array.isArray(fields)) {
    return []
  }
  return fields.filter(
    (item): item is FieldError =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as Record<string, unknown>).field === 'string' &&
      typeof (item as Record<string, unknown>).reason === 'string',
  )
}

/** Turns an error response (status and parsed body) into its typed error. */
export function errorFromResponse(status: number, body: unknown): ApiError {
  if (!isErrorBody(body)) {
    return new UnknownError(`The server answered with an unexpected response (HTTP ${status}).`, status, null)
  }
  const { code, message } = body
  switch (code) {
    case 'validation_failed':
      return new ValidationError(message, status, fieldErrors(body.fields))
    case 'not_authenticated':
      return new NotAuthenticatedError(message, status)
    case 'invalid_credentials':
      return new InvalidCredentialsError(message, status)
    case 'wrong_password':
      return new WrongPasswordError(message, status)
    case 'email_already_registered':
      return new EmailAlreadyRegisteredError(message, status)
    case 'not_found':
      return new NotFoundError(message, status)
    case 'no_matching_entries':
      return new NoMatchingEntriesError(message, status)
    case 'summary_input_too_large':
      return new SummaryInputTooLargeError(message, status)
    case 'limit_reached':
      return new LimitReachedError(
        message,
        status,
        typeof body.limit === 'string' && LIMIT_NAMES.includes(body.limit) ? body.limit : null,
      )
    case 'ai_unavailable':
      return new AiUnavailableError(message, status)
    case 'demo_account_not_deletable':
      return new DemoAccountNotDeletableError(message, status)
    default:
      return new UnknownError(message, status, code)
  }
}
