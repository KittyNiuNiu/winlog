// The central API client (product-spec.md §10.2). All backend calls go through src/api/;
// components import from here and never call fetch themselves (AGENTS.md, ESLint rule).
export { setLoginRedirect } from './client.ts'
export * from './errors.ts'
export * from './operations.ts'
export { getSession, type Session } from './session.ts'
export type * from './types.ts'
