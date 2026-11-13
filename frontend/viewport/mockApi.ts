import type { Page, Request, Route } from '@playwright/test'
import type { components } from '../src/api/schema'
import { API_BASE_URL } from './settings.ts'

// A stand-in for the backend: answers every request the app sends to API_BASE_URL through
// Playwright's request interception, with bodies typed from openapi.yaml (src/api/schema.d.ts).
// It keeps the entries and summaries in memory, so a save, edit or delete shows up on the
// next page as it would with the real API. It never calls an AI provider.

type Schemas = components['schemas']
export type Entry = Schemas['Entry']
export type EntryInput = Schemas['EntryInput']
export type Summary = Schemas['Summary']
export type SummaryFilter = Schemas['SummaryFilter']
export type Suggestion = Schemas['Suggestion']
type ApiError = Schemas['Error']
type Category = Schemas['Category']

export interface MockApiOptions {
  entries?: Entry[]
  summaries?: Summary[]
  /** `GET /entries` answers 500, so the page shows its load error. */
  failEntryList?: boolean
  /** `POST /auth/login` answers 401 `invalid_credentials`. */
  rejectLogin?: boolean
  /** What `POST /suggestions` answers. */
  suggestion?: Suggestion
  /** `POST /summaries` gets no answer until `releaseDraft()`, so the panel stays busy. */
  holdDraft?: boolean
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
  'Access-Control-Expose-Headers': 'Content-Disposition, Retry-After',
}

const ENTRY_PATH = /^\/entries\/([^/]+)$/
const SUMMARY_PATH = /^\/summaries\/([^/]+)$/

/** A token that is valid for the whole test (the clock is fixed). */
export const TOKEN_EXPIRES_AT = '2026-11-20T10:00:00Z'

export class MockApi {
  entries: Entry[]
  summaries: Summary[]
  readonly options: MockApiOptions
  /** Requests the mock has no answer for. A test fails when this is not empty. */
  readonly unanswered: string[] = []
  private created = 0
  private heldDraft: { route: Route; body: SummaryFilter } | null = null

  constructor(options: MockApiOptions = {}) {
    this.options = options
    this.entries = [...(options.entries ?? [])]
    this.summaries = [...(options.summaries ?? [])]
  }

  async install(page: Page): Promise<void> {
    await page.route(`${API_BASE_URL}/**`, (route) => this.answer(route))
  }

  /** Answers the held `POST /summaries`. */
  async releaseDraft(): Promise<void> {
    if (this.heldDraft !== null) {
      const { route, body } = this.heldDraft
      this.heldDraft = null
      await this.json(route, 201, this.newSummary(body))
    }
  }

  private async answer(route: Route): Promise<void> {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const path = url.pathname
    if (method === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS })
      return
    }

    const entryMatch = ENTRY_PATH.exec(path)
    const summaryMatch = SUMMARY_PATH.exec(path)
    const key = `${method} ${entryMatch ? '/entries/{id}' : summaryMatch ? '/summaries/{id}' : path}`

    switch (key) {
      case 'POST /auth/login':
        if (this.options.rejectLogin) {
          return this.error(route, 401, { code: 'invalid_credentials', message: 'Wrong email or password.' })
        }
        return this.json(route, 200, { token: 'test-token', expires_at: TOKEN_EXPIRES_AT } satisfies Schemas['LoginResult'])
      case 'POST /auth/demo':
        return this.json(route, 200, {
          token: 'demo-token',
          expires_at: TOKEN_EXPIRES_AT,
          demo: true,
        } satisfies Schemas['DemoLoginResult'])
      case 'POST /auth/logout':
        return this.empty(route)
      case 'GET /entries':
        if (this.options.failEntryList) {
          return this.error(route, 500, { code: 'internal_error', message: 'Something went wrong.' })
        }
        return this.json(route, 200, { entries: this.filteredEntries(url.searchParams) } satisfies Schemas['EntryList'])
      case 'POST /entries': {
        const entry = this.newEntry(bodyOf<EntryInput>(request))
        this.entries = [entry, ...this.entries]
        return this.json(route, 201, entry)
      }
      case 'GET /entries/{id}': {
        const entry = this.entries.find(({ id }) => id === entryMatch?.[1])
        return entry === undefined ? this.notFound(route) : this.json(route, 200, entry)
      }
      case 'PUT /entries/{id}': {
        const entry = this.entries.find(({ id }) => id === entryMatch?.[1])
        if (entry === undefined) {
          return this.notFound(route)
        }
        const input = bodyOf<EntryInput>(request)
        const updated: Entry = { ...this.newEntry(input), id: entry.id, created_at: entry.created_at }
        this.entries = this.entries.map((existing) => (existing.id === entry.id ? updated : existing))
        return this.json(route, 200, updated)
      }
      case 'DELETE /entries/{id}':
        this.entries = this.entries.filter(({ id }) => id !== entryMatch?.[1])
        return this.empty(route)
      case 'GET /tags':
        return this.json(route, 200, { tags: this.tagNames() } satisfies Schemas['TagList'])
      case 'POST /suggestions':
        return this.json(route, 200, this.options.suggestion ?? { category: 'Achievement', tags: [] })
      case 'GET /summaries':
        return this.json(route, 200, { summaries: this.summaries } satisfies Schemas['SummaryList'])
      case 'POST /summaries': {
        const body = bodyOf<SummaryFilter>(request)
        if (this.options.holdDraft) {
          this.heldDraft = { route, body }
          return undefined
        }
        return this.json(route, 201, this.newSummary(body))
      }
      case 'GET /summaries/{id}': {
        const summary = this.summaries.find(({ id }) => id === summaryMatch?.[1])
        return summary === undefined ? this.notFound(route) : this.json(route, 200, summary)
      }
      case 'PATCH /summaries/{id}': {
        const summary = this.summaries.find(({ id }) => id === summaryMatch?.[1])
        if (summary === undefined) {
          return this.notFound(route)
        }
        const updated: Summary = { ...summary, text: bodyOf<Schemas['SummaryUpdate']>(request).text }
        this.summaries = this.summaries.map((existing) => (existing.id === summary.id ? updated : existing))
        return this.json(route, 200, updated)
      }
      case 'DELETE /summaries/{id}':
        this.summaries = this.summaries.filter(({ id }) => id !== summaryMatch?.[1])
        return this.empty(route)
      default:
        this.unanswered.push(`${method} ${url.pathname}${url.search}`)
        return this.error(route, 500, { code: 'internal_error', message: 'Not mocked.' })
    }
  }

  /** `GET /entries` with its filters (openapi.yaml), newest first as the API sorts them. */
  private filteredEntries(query: URLSearchParams): Entry[] {
    const start = query.get('start_date')
    const end = query.get('end_date')
    const categories = query.getAll('category')
    const tags = query.getAll('tag').map((tag) => tag.toLowerCase())
    return this.entries
      .filter((entry) => start === null || entry.date >= start)
      .filter((entry) => end === null || entry.date <= end)
      .filter((entry) => categories.length === 0 || categories.includes(entry.category))
      .filter((entry) => tags.length === 0 || entry.tags.some((tag) => tags.includes(tag.toLowerCase())))
      .sort((a, b) => b.date.localeCompare(a.date) || b.created_at.localeCompare(a.created_at))
  }

  private tagNames(): string[] {
    const names = new Set(this.entries.flatMap((entry) => entry.tags))
    return [...names].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
  }

  private newEntry(input: EntryInput): Entry {
    this.created += 1
    const now = new Date().toISOString()
    return {
      id: `00000000-0000-4000-8000-${String(900 + this.created).padStart(12, '0')}`,
      date: input.date,
      text: input.text,
      category: input.category as Category,
      tags: input.tags ?? [],
      result_impact: input.result_impact?.trim() ? input.result_impact : null,
      created_at: now,
      updated_at: now,
    }
  }

  private newSummary(filter: SummaryFilter): Summary {
    this.created += 1
    const now = new Date().toISOString()
    const summary: Summary = {
      id: `00000000-0000-4000-9000-${String(900 + this.created).padStart(12, '0')}`,
      text: DRAFT_TEXT,
      filter,
      created_at: now,
      updated_at: now,
    }
    this.summaries = [summary, ...this.summaries]
    return summary
  }

  private json(route: Route, status: number, body: unknown): Promise<void> {
    return route.fulfill({ status, headers: CORS_HEADERS, contentType: 'application/json', body: JSON.stringify(body) })
  }

  private empty(route: Route): Promise<void> {
    return route.fulfill({ status: 204, headers: CORS_HEADERS })
  }

  private error(route: Route, status: number, body: ApiError): Promise<void> {
    return this.json(route, status, body)
  }

  private notFound(route: Route): Promise<void> {
    return this.error(route, 404, { code: 'not_found', message: 'Not found.' })
  }
}

function bodyOf<Body>(request: Request): Body {
  return request.postDataJSON() as Body
}

/** The text of a drafted summary. Fixed, so the screenshots are the same on every run. */
export const DRAFT_TEXT = [
  'From September to November 2026 you shipped the new onboarding flow, which cut setup time for new teams by half, and led the migration of the billing service without downtime.',
  '',
  'You also mentored two new colleagues and presented the accessibility audit to the whole department, which led to a shared checklist for every release.',
].join('\n')
