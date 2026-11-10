import type { RouteObject } from 'react-router'
import { GuestOnly, NotFoundRoute, RequireAuth } from './auth/RouteGuards.tsx'
import AppShell from './components/AppShell.tsx'
import AuthLayout from './components/AuthLayout.tsx'
import EntriesPage from './pages/EntriesPage.tsx'
import LoginPage from './pages/LoginPage.tsx'
import RegisterPage from './pages/RegisterPage.tsx'
import ReviewPage from './pages/ReviewPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import SummariesPage from './pages/SummariesPage.tsx'
import SummaryPage from './pages/SummaryPage.tsx'

// All client-side routes. Login and register have no app shell and are only for
// logged-out visitors. Every other page needs a login and is shown inside the app shell,
// except "Page not found", which anyone can see.
export const routes: RouteObject[] = [
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
          { path: 'review', element: <ReviewPage /> },
          { path: 'summaries', element: <SummariesPage /> },
          { path: 'summaries/:id', element: <SummaryPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundRoute /> },
]
