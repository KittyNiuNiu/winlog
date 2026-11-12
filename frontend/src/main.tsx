import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import '@fontsource-variable/bricolage-grotesque/opsz.css'
import '@fontsource-variable/figtree'
import { connectLoginRedirect } from './auth/loginRedirect.ts'
import './index.css'
import { routes } from './routes.tsx'

const router = createBrowserRouter(routes)
// A "not authenticated" response opens /login through the router, not a page reload.
connectLoginRedirect(router)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
