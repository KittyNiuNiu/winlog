import type { RouteObject } from 'react-router'
import AppShell from './components/AppShell.tsx'
import AuthLayout from './components/AuthLayout.tsx'
import EntriesPage from './pages/EntriesPage.tsx'
import LoginPage from './pages/LoginPage.tsx'
import NotFoundPage from './pages/NotFoundPage.tsx'
import RegisterPage from './pages/RegisterPage.tsx'
import ReviewPage from './pages/ReviewPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import SummariesPage from './pages/SummariesPage.tsx'
import SummaryPage from './pages/SummaryPage.tsx'

// All client-side routes. Login and register have no app shell; every other page,
// including "Page not found", is shown inside it.
export const routes: RouteObject[] = [
  {
    element: <AuthLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
    ],
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <EntriesPage /> },
      { path: 'review', element: <ReviewPage /> },
      { path: 'summaries', element: <SummariesPage /> },
      { path: 'summaries/:id', element: <SummaryPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
