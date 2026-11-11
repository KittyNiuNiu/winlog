import { render } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { routes } from '../routes.tsx'

// Renders the app's real route table at the given path, without a browser URL, with the
// API client's login redirect connected to the router as in main.tsx.
export function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  connectLoginRedirect(router)
  const result = render(<RouterProvider router={router} />)
  return { ...result, router }
}
