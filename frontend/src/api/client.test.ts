import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import type { operations as ContractOperations } from './schema'

// The contract, read with Node's fs because Vite serves only files inside frontend/ (npm test
// runs there). Node is reached through loose types, so the app's TypeScript program does not
// need Node's types.
const nodeFs: { readFileSync(path: string, encoding: 'utf8'): string } = await import(/* @vite-ignore */ `node:${'fs'}`)
const nodeProcess = (globalThis as unknown as { process: { cwd(): string } }).process
const openapiYaml = nodeFs.readFileSync(`${nodeProcess.cwd()}/../openapi.yaml`, 'utf8')

type Api = typeof import('./index.ts')
type ClientModule = typeof import('./client.ts')

const BASE_URL = 'http://api.test'
const STORAGE_KEY = 'winlog.session'
const FUTURE = '2099-01-01T00:00:00Z'
const ENTRY_ID = '0b6f3c1e-1d7a-4c5e-9f0a-2b3c4d5e6f70'
const SUMMARY_ID = '7e1d2c3b-4a59-4687-b5c4-d3e2f1a0b9c8'

const entry = {
  id: ENTRY_ID,
  date: '2026-11-01',
  text: 'Shipped the API client',
  category: 'Achievement',
  tags: ['frontend'],
  result_impact: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
} as const
const entryInput = { text: 'Shipped the API client', date: '2026-11-01', category: 'Achievement' } as const
const summaryFilter = { period_start: '2026-01-01', period_end: '2026-06-30' }
const summary = {
  id: SUMMARY_ID,
  text: 'A good half year.',
  filter: summaryFilter,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function noContent(): Response {
  return new Response(null, { status: 204 })
}

function errorResponse(status: number, code: string, extra: Record<string, unknown> = {}): Response {
  return jsonResponse(status, { code, message: `Server message for ${code}.`, ...extra })
}

function storeSession(session: { token: string; expiresAt: string; demo: boolean }): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

let api: Api
let client: ClientModule
let fetchMock: Mock<(request: Request) => Promise<Response>>
let redirectToLogin: Mock<() => void>

// A fresh copy of the client modules, as after a page reload: the in-memory session is
// read again from localStorage.
async function reload(): Promise<void> {
  vi.resetModules()
  api = await import('./index.ts')
  client = await import('./client.ts')
  api.setLoginRedirect(redirectToLogin)
}

function lastRequest(): Request {
  const call = fetchMock.mock.lastCall
  if (call === undefined) {
    throw new Error('fetch was not called')
  }
  return call[0]
}

beforeEach(async () => {
  localStorage.clear()
  vi.stubEnv('VITE_API_BASE_URL', BASE_URL)
  fetchMock = vi.fn<(request: Request) => Promise<Response>>()
  vi.stubGlobal('fetch', fetchMock)
  redirectToLogin = vi.fn<() => void>()
  await reload()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  localStorage.clear()
})

// --- One typed function per operation ---

interface OperationCase {
  call: (api: Api) => Promise<unknown>
  response: () => Response
}

const exportHeaders = (name: string, type: string) => ({
  'Content-Type': type,
  'Content-Disposition': `attachment; filename="${name}"`,
})

// Keyed by operationId: the type makes TypeScript require exactly the generated operations.
const operationCases: Record<keyof ContractOperations, OperationCase> = {
  getHealth: { call: (a) => a.getHealth(), response: () => jsonResponse(200, { status: 'ok', database: 'ok' }) },
  register: {
    call: (a) => a.register({ email: 'alice@example.com', password: 'Correct-Horse-7' }),
    response: () => jsonResponse(201, { id: ENTRY_ID, email: 'alice@example.com', created_at: FUTURE }),
  },
  login: {
    call: (a) => a.login({ email: 'alice@example.com', password: 'Correct-Horse-7' }),
    response: () => jsonResponse(200, { token: 'tok-new', expires_at: FUTURE }),
  },
  demoLogin: {
    call: (a) => a.demoLogin(),
    response: () => jsonResponse(200, { token: 'tok-demo', expires_at: FUTURE, demo: true }),
  },
  logout: { call: (a) => a.logout(), response: noContent },
  deleteAccount: { call: (a) => a.deleteAccount({ current_password: 'Correct-Horse-7' }), response: noContent },
  listEntries: { call: (a) => a.listEntries(), response: () => jsonResponse(200, { entries: [entry] }) },
  createEntry: { call: (a) => a.createEntry(entryInput), response: () => jsonResponse(201, entry) },
  getEntry: { call: (a) => a.getEntry(ENTRY_ID), response: () => jsonResponse(200, entry) },
  updateEntry: { call: (a) => a.updateEntry(ENTRY_ID, entryInput), response: () => jsonResponse(200, entry) },
  deleteEntry: { call: (a) => a.deleteEntry(ENTRY_ID), response: noContent },
  listTags: { call: (a) => a.listTags(), response: () => jsonResponse(200, { tags: ['frontend'] }) },
  suggestCategoryAndTags: {
    call: (a) => a.suggestCategoryAndTags({ text: 'Shipped it' }),
    response: () => jsonResponse(200, { category: 'Achievement', tags: [] }),
  },
  listSummaries: { call: (a) => a.listSummaries(), response: () => jsonResponse(200, { summaries: [summary] }) },
  generateSummary: { call: (a) => a.generateSummary(summaryFilter), response: () => jsonResponse(201, summary) },
  getSummary: { call: (a) => a.getSummary(SUMMARY_ID), response: () => jsonResponse(200, summary) },
  updateSummary: {
    call: (a) => a.updateSummary(SUMMARY_ID, { text: 'Edited.' }),
    response: () => jsonResponse(200, summary),
  },
  deleteSummary: { call: (a) => a.deleteSummary(SUMMARY_ID), response: noContent },
  exportJson: {
    call: (a) => a.exportJson(),
    response: () =>
      new Response('{"format_version":1}', {
        status: 200,
        headers: exportHeaders('winlog-export-2026-11-01.json', 'application/json'),
      }),
  },
  exportMarkdown: {
    call: (a) => a.exportMarkdown(),
    response: () =>
      new Response('# Winlog export\n', {
        status: 200,
        headers: exportHeaders('winlog-export-2026-11-01.md', 'text/markdown'),
      }),
  },
}

interface ContractOperation {
  operationId: string
  method: string
  path: string
  isPublic: boolean
}

// Reads every operation from openapi.yaml: its path, method, operationId and whether it has
// `security: []` (no token needed).
function contractOperations(): ContractOperation[] {
  const operations: ContractOperation[] = []
  let path = ''
  let method = ''
  for (const line of openapiYaml.split('\n')) {
    const pathMatch = /^ {2}(\/\S*):\s*$/.exec(line)
    const methodMatch = /^ {4}(get|put|post|patch|delete):\s*$/.exec(line)
    const idMatch = /^ {6}operationId:\s*(\w+)\s*$/.exec(line)
    if (pathMatch) {
      path = pathMatch[1]
    } else if (methodMatch) {
      method = methodMatch[1].toUpperCase()
    } else if (idMatch) {
      operations.push({ operationId: idMatch[1], method, path, isPublic: false })
    } else if (/^ {6}security:\s*\[\]\s*$/.test(line)) {
      operations[operations.length - 1].isPublic = true
    }
  }
  return operations
}

const operations = contractOperations()

function expectedUrl(path: string): string {
  return BASE_URL + path.replace('{entryId}', ENTRY_ID).replace('{summaryId}', SUMMARY_ID)
}

describe('operations', () => {
  it('has one function per operation in openapi.yaml, and no others', () => {
    expect(operations).toHaveLength(20)
    const operationIds = operations.map((operation) => operation.operationId).sort()
    expect(Object.keys(operationCases).sort()).toEqual(operationIds)
    for (const operationId of operationIds) {
      expect(typeof (api as unknown as Record<string, unknown>)[operationId]).toBe('function')
    }
  })

  it('treats exactly the operations with "security: []" as public', () => {
    const contractPublic = operations.filter((o) => o.isPublic).map((o) => `${o.method} ${o.path}`)
    expect([...client.PUBLIC_OPERATIONS].sort()).toEqual(contractPublic.sort())
  })

  describe.each(operations)('$operationId', ({ operationId, method, path, isPublic }) => {
    it(`calls ${method} ${path} on the configured base URL`, async () => {
      const operation = operationCases[operationId as keyof ContractOperations]
      fetchMock.mockResolvedValueOnce(operation.response())
      await operation.call(api)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(lastRequest().method).toBe(method)
      expect(lastRequest().url).toBe(expectedUrl(path))
    })

    if (isPublic) {
      it('sends no Authorization header, even with a stored token', async () => {
        storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: false })
        await reload()
        const operation = operationCases[operationId as keyof ContractOperations]
        fetchMock.mockResolvedValueOnce(operation.response())
        await operation.call(api)
        expect(lastRequest().headers.has('Authorization')).toBe(false)
      })
    } else {
      it('sends "Authorization: Bearer <token>" with the stored token', async () => {
        storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: false })
        await reload()
        const operation = operationCases[operationId as keyof ContractOperations]
        fetchMock.mockResolvedValueOnce(operation.response())
        await operation.call(api)
        expect(lastRequest().headers.get('Authorization')).toBe('Bearer tok-1')
      })
    }
  })

  it('sends the request body as JSON', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, entry))
    await expect(api.createEntry(entryInput)).resolves.toEqual(entry)
    expect(lastRequest().headers.get('Content-Type')).toBe('application/json')
    await expect(lastRequest().json()).resolves.toEqual(entryInput)
  })

  it('sends the current password with account deletion', async () => {
    fetchMock.mockResolvedValueOnce(noContent())
    await api.deleteAccount({ current_password: 'Correct-Horse-7' })
    await expect(lastRequest().json()).resolves.toEqual({ current_password: 'Correct-Horse-7' })
  })

  it('sends entry filters as repeated query parameters', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { entries: [] }))
    await api.listEntries({
      start_date: '2026-01-01',
      end_date: '2026-06-30',
      category: ['Achievement', 'Side project'],
      tag: ['a,b', 'c'],
    })
    const params = new URL(lastRequest().url).searchParams
    expect(params.get('start_date')).toBe('2026-01-01')
    expect(params.get('end_date')).toBe('2026-06-30')
    expect(params.getAll('category')).toEqual(['Achievement', 'Side project'])
    expect(params.getAll('tag')).toEqual(['a,b', 'c'])
  })

  it('returns the response data', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tags: ['frontend', 'mentoring'] }))
    await expect(api.listTags()).resolves.toEqual({ tags: ['frontend', 'mentoring'] })
  })
})

// --- Base URL ---

describe('base URL', () => {
  it('ignores a trailing slash', async () => {
    vi.stubEnv('VITE_API_BASE_URL', `${BASE_URL}/`)
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tags: [] }))
    await api.listTags()
    expect(lastRequest().url).toBe(`${BASE_URL}/tags`)
  })

  it('gives an unknown error without calling fetch when VITE_API_BASE_URL is not set', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    const error = await api.listTags().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.UnknownError)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

// --- Token ---

describe('token', () => {
  it('sends no Authorization header when no token is stored', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { entries: [] }))
    await api.listEntries()
    expect(lastRequest().headers.has('Authorization')).toBe(false)
  })

  it('stores the token after login, and it survives a reload', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-new', expires_at: FUTURE }))
    await api.login({ email: 'alice@example.com', password: 'Correct-Horse-7' })
    expect(api.getSession()).toEqual({ token: 'tok-new', expiresAt: FUTURE, demo: false })
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')).toEqual({
      token: 'tok-new',
      expiresAt: FUTURE,
      demo: false,
    })

    await reload()
    expect(api.getSession()).toEqual({ token: 'tok-new', expiresAt: FUTURE, demo: false })
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tags: [] }))
    await api.listTags()
    expect(lastRequest().headers.get('Authorization')).toBe('Bearer tok-new')
  })

  it('stores the token and the demo flag after demo-login, and both survive a reload', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-demo', expires_at: FUTURE, demo: true }))
    await api.demoLogin()
    expect(api.getSession()).toEqual({ token: 'tok-demo', expiresAt: FUTURE, demo: true })

    await reload()
    expect(api.getSession()?.demo).toBe(true)
  })

  it('replaces a demo session with a normal one on login', async () => {
    storeSession({ token: 'tok-demo', expiresAt: FUTURE, demo: true })
    await reload()
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-new', expires_at: FUTURE }))
    await api.login({ email: 'alice@example.com', password: 'Correct-Horse-7' })
    expect(api.getSession()).toEqual({ token: 'tok-new', expiresAt: FUTURE, demo: false })
  })

  it('does not store anything when login fails', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(401, 'invalid_credentials'))
    await expect(api.login({ email: 'alice@example.com', password: 'wrong' })).rejects.toBeInstanceOf(
      api.InvalidCredentialsError,
    )
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('removes an expired token and does not send it', async () => {
    storeSession({ token: 'tok-old', expiresAt: '2020-01-01T00:00:00Z', demo: true })
    await reload()
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tags: [] }))
    await api.listTags()
    expect(lastRequest().headers.has('Authorization')).toBe(false)
  })

  it('removes the token once it expires during the session', async () => {
    vi.useFakeTimers({ now: new Date('2026-11-10T12:00:00Z') })
    storeSession({ token: 'tok-1', expiresAt: '2026-11-10T13:00:00Z', demo: false })
    await reload()
    expect(api.getSession()?.token).toBe('tok-1')
    vi.setSystemTime(new Date('2026-11-10T13:00:00Z'))
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('ignores and removes a stored value it cannot read', async () => {
    for (const stored of ['not json', '{"token":"tok-1"}', '"tok-1"', 'null']) {
      localStorage.setItem(STORAGE_KEY, stored)
      await reload()
      expect(api.getSession()).toBeNull()
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    }
  })
})

// --- Logout and account deletion ---

describe('logout', () => {
  beforeEach(async () => {
    storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: true })
    await reload()
  })

  it('removes the token and demo flag after a successful logout', async () => {
    fetchMock.mockResolvedValueOnce(noContent())
    await api.logout()
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('removes the token and demo flag even if the server fails', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(500, 'internal_error'))
    await expect(api.logout()).rejects.toBeInstanceOf(api.UnknownError)
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('removes the token and demo flag even if the network fails', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api.logout()).rejects.toBeInstanceOf(api.NetworkError)
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})

describe('account deletion', () => {
  beforeEach(async () => {
    storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: false })
    await reload()
  })

  it('removes the token and demo flag after a successful deletion', async () => {
    fetchMock.mockResolvedValueOnce(noContent())
    await api.deleteAccount({ current_password: 'Correct-Horse-7' })
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it.each([
    ['a wrong password', () => errorResponse(403, 'wrong_password'), 'WrongPasswordError'],
    ['the demo error', () => errorResponse(409, 'demo_account_not_deletable'), 'DemoAccountNotDeletableError'],
    [
      'a validation error',
      () => errorResponse(422, 'validation_failed', { fields: [{ field: 'current_password', reason: 'Required.' }] }),
      'ValidationError',
    ],
    ['an unknown error', () => errorResponse(500, 'internal_error'), 'UnknownError'],
  ] as const)('keeps the session after %s', async (_label, response, errorName) => {
    fetchMock.mockResolvedValueOnce(response())
    const error = await api.deleteAccount({ current_password: 'wrong' }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api[errorName])
    expect(api.getSession()?.token).toBe('tok-1')
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull()
    expect(redirectToLogin).not.toHaveBeenCalled()
  })

  it('keeps the session after a network error', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api.deleteAccount({ current_password: 'Correct-Horse-7' })).rejects.toBeInstanceOf(
      api.NetworkError,
    )
    expect(api.getSession()?.token).toBe('tok-1')
  })

  it('removes the session and redirects to /login on "not authenticated"', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(401, 'not_authenticated'))
    await expect(api.deleteAccount({ current_password: 'Correct-Horse-7' })).rejects.toBeInstanceOf(
      api.NotAuthenticatedError,
    )
    expect(api.getSession()).toBeNull()
    expect(redirectToLogin).toHaveBeenCalledTimes(1)
  })
})

// --- "Not authenticated" ---

describe('not authenticated', () => {
  beforeEach(async () => {
    storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: true })
    await reload()
  })

  it('removes the token and demo flag and sends the user to /login', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(401, 'not_authenticated'))
    const error = await api.listEntries().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.NotAuthenticatedError)
    expect(api.getSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    expect(redirectToLogin).toHaveBeenCalledTimes(1)
  })

  it('does the same for a download', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(401, 'not_authenticated'))
    await expect(api.exportJson()).rejects.toBeInstanceOf(api.NotAuthenticatedError)
    expect(api.getSession()).toBeNull()
    expect(redirectToLogin).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['login', (a: Api) => a.login({ email: 'alice@example.com', password: 'x' })],
    ['demo-login', (a: Api) => a.demoLogin()],
  ])('is not applied to %s', async (_label, call) => {
    for (const code of ['invalid_credentials', 'not_authenticated']) {
      fetchMock.mockResolvedValueOnce(errorResponse(401, code))
      await expect(call(api)).rejects.toBeInstanceOf(api.ApiError)
    }
    expect(redirectToLogin).not.toHaveBeenCalled()
    expect(api.getSession()?.token).toBe('tok-1')
  })

  it('is not applied to other errors', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, 'not_found'))
    await expect(api.getEntry(ENTRY_ID)).rejects.toBeInstanceOf(api.NotFoundError)
    expect(redirectToLogin).not.toHaveBeenCalled()
    expect(api.getSession()?.token).toBe('tok-1')
  })
})

// --- Typed errors ---

describe('typed errors', () => {
  it.each([
    ['validation_failed', 422, 'ValidationError'],
    ['not_authenticated', 401, 'NotAuthenticatedError'],
    ['invalid_credentials', 401, 'InvalidCredentialsError'],
    ['wrong_password', 403, 'WrongPasswordError'],
    ['email_already_registered', 409, 'EmailAlreadyRegisteredError'],
    ['not_found', 404, 'NotFoundError'],
    ['no_matching_entries', 422, 'NoMatchingEntriesError'],
    ['summary_input_too_large', 422, 'SummaryInputTooLargeError'],
    ['limit_reached', 429, 'LimitReachedError'],
    ['ai_unavailable', 503, 'AiUnavailableError'],
    ['demo_account_not_deletable', 409, 'DemoAccountNotDeletableError'],
  ] as const)('turns "%s" into its own typed error', async (code, status, errorName) => {
    fetchMock.mockResolvedValueOnce(errorResponse(status, code))
    const error = await api.generateSummary(summaryFilter).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api[errorName])
    expect(error).toBeInstanceOf(api.ApiError)
    expect(error).toMatchObject({ name: errorName, status, message: `Server message for ${code}.` })
  })

  it('gives each typed error its own class', () => {
    const names = [
      api.ValidationError,
      api.NotAuthenticatedError,
      api.InvalidCredentialsError,
      api.WrongPasswordError,
      api.EmailAlreadyRegisteredError,
      api.NotFoundError,
      api.NoMatchingEntriesError,
      api.SummaryInputTooLargeError,
      api.LimitReachedError,
      api.AiUnavailableError,
      api.DemoAccountNotDeletableError,
      api.NetworkError,
      api.UnknownError,
    ]
    expect(new Set(names).size).toBe(names.length)
  })

  it('lists the failing fields of a validation error', async () => {
    const fields = [
      { field: 'text', reason: 'Text must not be empty.' },
      { field: 'date', reason: 'Date is required.' },
    ]
    fetchMock.mockResolvedValueOnce(errorResponse(422, 'validation_failed', { fields }))
    const error = await api.createEntry(entryInput).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.ValidationError)
    expect((error as InstanceType<Api['ValidationError']>).fields).toEqual(fields)
  })

  it('gives a validation error without fields an empty list', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(422, 'validation_failed'))
    const error = await api.createEntry(entryInput).catch((e: unknown) => e)
    expect((error as InstanceType<Api['ValidationError']>).fields).toEqual([])
  })

  it.each(['user_suggestions', 'user_summaries', 'global'] as const)(
    'says which limit was reached: %s',
    async (limit) => {
      fetchMock.mockResolvedValueOnce(errorResponse(429, 'limit_reached', { limit }))
      const error = await api.suggestCategoryAndTags({ text: 'x' }).catch((e: unknown) => e)
      expect(error).toBeInstanceOf(api.LimitReachedError)
      expect((error as InstanceType<Api['LimitReachedError']>).limit).toBe(limit)
    },
  )

  it('gives a limit error with an unknown limit name the limit null', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(429, 'limit_reached', { limit: 'weekly' }))
    const error = await api.suggestCategoryAndTags({ text: 'x' }).catch((e: unknown) => e)
    expect((error as InstanceType<Api['LimitReachedError']>).limit).toBeNull()
  })

  it('turns the demo-login "not found" into a not-found error', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, 'not_found'))
    await expect(api.demoLogin()).rejects.toBeInstanceOf(api.NotFoundError)
  })
})

// --- Network and unknown errors ---

describe('network and unknown errors', () => {
  it('turns a failed request into a network error', async () => {
    const cause = new TypeError('Failed to fetch')
    fetchMock.mockRejectedValueOnce(cause)
    const error = await api.listTags().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.NetworkError)
    expect(error).toMatchObject({ status: null, cause })
  })

  it.each([
    ['internal_error', 500],
    ['database_unreachable', 503],
    ['method_not_allowed', 405],
  ])('turns "%s" into an unknown error with its status and code', async (code, status) => {
    fetchMock.mockResolvedValueOnce(errorResponse(status, code))
    const error = await api.getHealth().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.UnknownError)
    expect(error).toMatchObject({ status, code, message: `Server message for ${code}.` })
  })

  it('turns an error response that is not JSON into an unknown error', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }),
    )
    const error = await api.listTags().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.UnknownError)
    expect(error).toMatchObject({ status: 502, code: null })
  })

  it('turns an error response without a code into an unknown error', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(500, { detail: 'boom' }))
    await expect(api.listTags()).rejects.toBeInstanceOf(api.UnknownError)
  })

  it('turns an empty error response into an unknown error', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 500 }))
    const error = await api.listTags().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(api.UnknownError)
    expect(error).toMatchObject({ status: 500 })
  })

  it('turns a success response that is not JSON into an unknown error', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('<!doctype html><title>Winlog</title>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    )
    await expect(api.listTags()).rejects.toBeInstanceOf(api.UnknownError)
  })
})

// --- No timeout ---

describe('timeout', () => {
  it('sets no timeout of its own, so a slow summary still arrives', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementationOnce(
      (request) =>
        new Promise((resolve, reject) => {
          request.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          setTimeout(() => resolve(jsonResponse(201, summary)), 150_000)
        }),
    )
    const pending = api.generateSummary(summaryFilter)
    await vi.advanceTimersByTimeAsync(150_000)
    await expect(pending).resolves.toEqual(summary)
    expect(lastRequest().signal.aborted).toBe(false)
  })
})

// --- Blocked storage ---

describe('blocked storage', () => {
  function blockStorage(): void {
    const blocked = () => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    }
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(blocked)
  }

  it('does not crash, and keeps the login in memory until the next reload', async () => {
    blockStorage()
    await reload()
    expect(api.getSession()).toBeNull()

    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-mem', expires_at: FUTURE, demo: true }))
    await api.demoLogin()
    expect(api.getSession()).toEqual({ token: 'tok-mem', expiresAt: FUTURE, demo: true })
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tags: [] }))
    await api.listTags()
    expect(lastRequest().headers.get('Authorization')).toBe('Bearer tok-mem')

    fetchMock.mockResolvedValueOnce(noContent())
    await api.logout()
    expect(api.getSession()).toBeNull()

    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-mem', expires_at: FUTURE }))
    await api.login({ email: 'alice@example.com', password: 'Correct-Horse-7' })
    await reload()
    expect(api.getSession()).toBeNull()
  })

  it('does not crash when localStorage itself cannot be accessed', async () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
    await reload()
    expect(api.getSession()).toBeNull()

    fetchMock.mockResolvedValueOnce(jsonResponse(200, { token: 'tok-mem', expires_at: FUTURE }))
    await api.login({ email: 'alice@example.com', password: 'Correct-Horse-7' })
    expect(api.getSession()?.token).toBe('tok-mem')

    fetchMock.mockResolvedValueOnce(errorResponse(401, 'not_authenticated'))
    await expect(api.listTags()).rejects.toBeInstanceOf(api.NotAuthenticatedError)
    expect(api.getSession()).toBeNull()
    expect(redirectToLogin).toHaveBeenCalledTimes(1)
  })
})

// --- Downloads ---

describe('downloads', () => {
  beforeEach(async () => {
    storeSession({ token: 'tok-1', expiresAt: FUTURE, demo: false })
    await reload()
  })

  it('returns the JSON export contents and the file name from Content-Disposition', async () => {
    const body = JSON.stringify({ format_version: 1, exported_at: FUTURE, entries: [entry], summaries: [] })
    fetchMock.mockResolvedValueOnce(
      new Response(body, { status: 200, headers: exportHeaders('winlog-export-2026-11-01.json', 'application/json') }),
    )
    const file = await api.exportJson()
    expect(lastRequest().headers.get('Authorization')).toBe('Bearer tok-1')
    expect(file.filename).toBe('winlog-export-2026-11-01.json')
    expect(file.contents.type).toBe('application/json')
    await expect(file.contents.text()).resolves.toBe(body)
  })

  it('returns the Markdown export contents and the file name from Content-Disposition', async () => {
    const body = '# Winlog export\n\nExported on 2026-11-01\n\n## Entries\n\nNone\n\n## Summaries\n\nNone\n'
    fetchMock.mockResolvedValueOnce(
      new Response(body, { status: 200, headers: exportHeaders('winlog-export-2026-11-01.md', 'text/markdown') }),
    )
    const file = await api.exportMarkdown()
    expect(lastRequest().headers.get('Authorization')).toBe('Bearer tok-1')
    expect(file.filename).toBe('winlog-export-2026-11-01.md')
    await expect(file.contents.text()).resolves.toBe(body)
  })

  it('gives an unknown error when the file name is missing', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await expect(api.exportJson()).rejects.toBeInstanceOf(api.UnknownError)
  })
})
