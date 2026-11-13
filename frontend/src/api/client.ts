// The low-level client: openapi-fetch with the types generated from openapi.yaml, plus the
// token header, error mapping and the "not authenticated" redirect. Operations call `send`;
// nothing outside src/api/ uses this file directly.
import createClient, { type Client, type Middleware } from 'openapi-fetch'
import { ApiError, NetworkError, NotAuthenticatedError, UnknownError, errorFromResponse } from './errors.ts'
import type { paths } from './schema'
import { clearSession, getSession } from './session.ts'

/** Operations that need no token (`security: []` in openapi.yaml), as "METHOD path". */
export const PUBLIC_OPERATIONS: ReadonlySet<string> = new Set([
  'GET /health',
  'POST /auth/register',
  'POST /auth/login',
  'POST /auth/demo',
])

const LOGIN_PATH = '/login'

function defaultLoginRedirect(): void {
  if (window.location.pathname !== LOGIN_PATH) {
    window.location.assign(LOGIN_PATH)
  }
}

let loginRedirect: () => void = defaultLoginRedirect

/**
 * Replaces how the client sends the user to `/login` after a "not authenticated" response,
 * for example with the router's navigate function. By default it loads `/login`.
 */
export function setLoginRedirect(redirect: () => void): void {
  loginRedirect = redirect
}

/** The backend base URL from the Vite build-time variable, or null when it is not set. */
export function apiBaseUrl(): string | null {
  const value = import.meta.env.VITE_API_BASE_URL
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
}

const authHeader: Middleware = {
  onRequest({ request, schemaPath }) {
    if (PUBLIC_OPERATIONS.has(`${request.method} ${schemaPath}`)) {
      return undefined
    }
    const session = getSession()
    if (session !== null) {
      request.headers.set('Authorization', `Bearer ${session.token}`)
    }
    return request
  },
}

// No timeout and no AbortSignal: a summary may take up to 60 seconds (#13), and the hosted
// app can need about a minute to wake up (product-spec.md §12).
async function fetchOrNetworkError(request: Request): Promise<Response> {
  try {
    // Looked up on every call, so tests can replace the global fetch.
    return await globalThis.fetch(request)
  } catch (cause) {
    throw new NetworkError({ cause })
  }
}

type ApiClient = Client<paths>

let cached: { baseUrl: string; client: ApiClient } | null = null

function client(): ApiClient {
  const baseUrl = apiBaseUrl()
  if (baseUrl === null) {
    throw new UnknownError('The API base URL is not configured (VITE_API_BASE_URL).', null, null)
  }
  if (cached === null || cached.baseUrl !== baseUrl) {
    const created = createClient<paths>({ baseUrl, fetch: fetchOrNetworkError })
    created.use(authHeader)
    cached = { baseUrl, client: created }
  }
  return cached.client
}

interface ApiResult<Data> {
  data?: Data
  error?: unknown
  response: Response
}

export interface SendOptions {
  /** False for login and demo-login: their errors never end the session. Default true. */
  redirectOnNotAuthenticated?: boolean
}

/**
 * Runs one request and returns its data, or throws the matching `ApiError`. A "not
 * authenticated" response removes the stored session and sends the user to `/login`.
 */
export async function send<Data>(
  perform: (api: ApiClient) => Promise<ApiResult<Data>>,
  { redirectOnNotAuthenticated = true }: SendOptions = {},
): Promise<{ data: Data; response: Response }> {
  let result: ApiResult<Data>
  try {
    result = await perform(client())
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    // For example a success response whose body is not valid JSON.
    throw new UnknownError('The server answered with an unexpected response.', null, null, { cause: error })
  }

  const { response } = result
  if (!response.ok) {
    // Retry-After is readable cross-origin because the backend exposes it (CORS, #46).
    const error = errorFromResponse(response.status, result.error, response.headers.get('Retry-After'))
    if (error instanceof NotAuthenticatedError && redirectOnNotAuthenticated) {
      clearSession()
      loginRedirect()
    }
    throw error
  }
  return { data: result.data as Data, response }
}
