// Frontend tests never reach a real server (#73). Before each test the global fetch is
// replaced with a stub that rejects the way fetch does when no server answers, so a test
// that mocks only some API operations behaves the same whether or not a backend runs on
// VITE_API_BASE_URL. The API client turns the rejection into a NetworkError, as it does for
// an unreachable backend. Tests that need responses install their own fetch stub with
// vi.stubGlobal (for example src/api/client.test.ts); the next test gets this one again.
import { vi } from 'vitest'

export function unreachableFetch(input: RequestInfo | URL): Promise<Response> {
  const url = input instanceof Request ? input.url : String(input)
  return Promise.reject(
    new TypeError('fetch failed', {
      cause: new Error(`Tests do not reach a real server (request to ${url}).`),
    }),
  )
}

export function blockNetwork(): void {
  vi.stubGlobal('fetch', unreachableFetch)
}
