import { render } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { routes } from '../routes.tsx'

// Renders the app's real route table at the given path, without a browser URL.
export function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const result = render(<RouterProvider router={router} />)
  return { ...result, router }
}
