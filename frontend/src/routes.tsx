import type { RouteObject } from 'react-router'
import { GuestOnly, NotFoundRoute, RequireAuth } from './auth/RouteGuards.tsx'
import AppShell from './components/AppShell.tsx'
import AuthLayout from './components/AuthLayout.tsx'
import EditEntryPage from './pages/EditEntryPage.tsx'
import EntriesPage from './pages/EntriesPage.tsx'
import LoginPage from './pages/LoginPage.tsx'
import NewEntryPage from './pages/NewEntryPage.tsx'
import RegisterPage from './pages/RegisterPage.tsx'
import ReviewPage from './pages/ReviewPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import SummariesPage from './pages/SummariesPage.tsx'
import SummaryPage from './pages/SummaryPage.tsx'

/**
 * All client-side routes. Login and register have no app shell and are only for
 * logged-out visitors. Every other page needs a login and is shown inside the app shell,
 * except "Page not found", which anyone can see, and the development-only pages in
 * `devRoutes`, which need no login and have no app shell.
 */
export function createRoutes(devRoutes: RouteObject[]): RouteObject[] {
  return [
    {
      element: <GuestOnly />,
      children: [
        {
          element: <AuthLayout />,
          children: [
            { path: '/login', element: <LoginPage /> },
            { path: '/register', element: <RegisterPage /> },
          ],
        },
      ],
    },
    {
      element: <RequireAuth />,
      children: [
        {
          path: '/',
          element: <AppShell />,
          children: [
            { index: true, element: <EntriesPage /> },
            { path: 'entries/new', element: <NewEntryPage /> },
            { path: 'entries/:id/edit', element: <EditEntryPage /> },
            { path: 'review', element: <ReviewPage /> },
            { path: 'summaries', element: <SummariesPage /> },
            { path: 'summaries/:id', element: <SummaryPage /> },
            { path: 'settings', element: <SettingsPage /> },
          ],
        },
      ],
    },
    ...devRoutes,
    { path: '*', element: <NotFoundRoute /> },
  ]
}

/** The component preview, only with `npm run dev`. */
export const DEV_PREVIEW_PATH = '/dev/components'

// The condition must stay inline: in the production build it is the constant `false`, so
// the bundler drops the preview page and its import from the build entirely.
export const routes: RouteObject[] = createRoutes(
  import.meta.env.DEV
    ? [
        {
          path: DEV_PREVIEW_PATH,
          lazy: async () => ({ Component: (await import('./pages/dev/ComponentPreviewPage.tsx')).default }),
        },
      ]
    : [],
)
