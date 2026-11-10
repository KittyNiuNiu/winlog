// One typed function per operation in openapi.yaml, named after its operationId. Each
// returns the response data or throws an ApiError (see errors.ts).
import { send } from './client.ts'
import { filenameFromContentDisposition } from './contentDisposition.ts'
import { UnknownError } from './errors.ts'
import { clearSession, saveSession } from './session.ts'
import type {
  AccountDeletion,
  Credentials,
  DemoLoginResult,
  Entry,
  EntryInput,
  EntryList,
  EntryListQuery,
  Health,
  LoginResult,
  Registration,
  Suggestion,
  SuggestionRequest,
  Summary,
  SummaryFilter,
  SummaryList,
  SummaryUpdate,
  TagList,
  User,
} from './types.ts'

// --- Health ---

/** `GET /health`: checks that the API and the database are up. */
export async function getHealth(): Promise<Health> {
  return (await send((api) => api.GET('/health'))).data
}

// --- Accounts ---

/** `POST /auth/register`: creates an account. Returns no token; log in afterwards. */
export async function register(body: Registration): Promise<User> {
  return (await send((api) => api.POST('/auth/register', { body }))).data
}

/** `POST /auth/login`: logs in and stores the token. */
export async function login(body: Credentials): Promise<LoginResult> {
  const { data } = await send((api) => api.POST('/auth/login', { body }), { redirectOnNotAuthenticated: false })
  saveSession({ token: data.token, expiresAt: data.expires_at, demo: false })
  return data
}

/** `POST /auth/demo`: logs in to the shared demo account and stores the token and demo flag. */
export async function demoLogin(): Promise<DemoLoginResult> {
  const { data } = await send((api) => api.POST('/auth/demo'), { redirectOnNotAuthenticated: false })
  saveSession({ token: data.token, expiresAt: data.expires_at, demo: true })
  return data
}

/** `POST /auth/logout`: revokes the token. The stored session is removed even if this fails. */
export async function logout(): Promise<void> {
  try {
    await send((api) => api.POST('/auth/logout'))
  } finally {
    clearSession()
  }
}

/**
 * `DELETE /account`: deletes the account and all of its data. The stored session is removed
 * only when the deletion succeeds, or by the general "not authenticated" rule. After a wrong
 * password, the demo error or any other failure the user stays logged in (#34, #35).
 */
export async function deleteAccount(body: AccountDeletion): Promise<void> {
  await send((api) => api.DELETE('/account', { body }))
  clearSession()
}

// --- Entries ---

/** `GET /entries`: lists the user's entries, optionally filtered. */
export async function listEntries(query: EntryListQuery = {}): Promise<EntryList> {
  return (await send((api) => api.GET('/entries', { params: { query } }))).data
}

/** `POST /entries`: creates one entry. */
export async function createEntry(body: EntryInput): Promise<Entry> {
  return (await send((api) => api.POST('/entries', { body }))).data
}

/** `GET /entries/{entryId}`: gets one entry. */
export async function getEntry(entryId: string): Promise<Entry> {
  return (await send((api) => api.GET('/entries/{entryId}', { params: { path: { entryId } } }))).data
}

/** `PUT /entries/{entryId}`: replaces one entry. */
export async function updateEntry(entryId: string, body: EntryInput): Promise<Entry> {
  return (await send((api) => api.PUT('/entries/{entryId}', { params: { path: { entryId } }, body }))).data
}

/** `DELETE /entries/{entryId}`: deletes one entry. */
export async function deleteEntry(entryId: string): Promise<void> {
  await send((api) => api.DELETE('/entries/{entryId}', { params: { path: { entryId } } }))
}

// --- Tags ---

/** `GET /tags`: lists the user's tags that at least one entry uses. */
export async function listTags(): Promise<TagList> {
  return (await send((api) => api.GET('/tags'))).data
}

// --- AI ---

/** `POST /suggestions`: gets AI suggestions for an entry's category and tags. */
export async function suggestCategoryAndTags(body: SuggestionRequest): Promise<Suggestion> {
  return (await send((api) => api.POST('/suggestions', { body }))).data
}

// --- Summaries ---

/** `GET /summaries`: lists the user's saved summaries. */
export async function listSummaries(): Promise<SummaryList> {
  return (await send((api) => api.GET('/summaries'))).data
}

/** `POST /summaries`: generates a summary of the matching entries and saves it. */
export async function generateSummary(body: SummaryFilter): Promise<Summary> {
  return (await send((api) => api.POST('/summaries', { body }))).data
}

/** `GET /summaries/{summaryId}`: gets one summary. */
export async function getSummary(summaryId: string): Promise<Summary> {
  return (await send((api) => api.GET('/summaries/{summaryId}', { params: { path: { summaryId } } }))).data
}

/** `PATCH /summaries/{summaryId}`: changes the text of one summary. */
export async function updateSummary(summaryId: string, body: SummaryUpdate): Promise<Summary> {
  return (await send((api) => api.PATCH('/summaries/{summaryId}', { params: { path: { summaryId } }, body }))).data
}

/** `DELETE /summaries/{summaryId}`: deletes one summary. */
export async function deleteSummary(summaryId: string): Promise<void> {
  await send((api) => api.DELETE('/summaries/{summaryId}', { params: { path: { summaryId } } }))
}

// --- Export ---

/** A downloaded export file, ready for the browser to save. */
export interface DownloadedFile {
  /** The file contents. */
  contents: Blob
  /** The file name the server sent in Content-Disposition. */
  filename: string
}

function downloadedFile(contents: Blob, response: Response): DownloadedFile {
  const filename = filenameFromContentDisposition(response.headers.get('Content-Disposition'))
  if (filename === null) {
    throw new UnknownError('The export has no file name (Content-Disposition).', response.status, null)
  }
  return { contents, filename }
}

/** `GET /export/json`: downloads all entries and summaries as JSON. */
export async function exportJson(): Promise<DownloadedFile> {
  const { data, response } = await send((api) => api.GET('/export/json', { parseAs: 'blob' }))
  return downloadedFile(data, response)
}

/** `GET /export/markdown`: downloads all entries and summaries as Markdown. */
export async function exportMarkdown(): Promise<DownloadedFile> {
  const { data, response } = await send((api) => api.GET('/export/markdown', { parseAs: 'blob' }))
  return downloadedFile(data, response)
}
