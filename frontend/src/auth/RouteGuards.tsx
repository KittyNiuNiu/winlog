import { Navigate, Outlet, useLocation } from 'react-router'
import { getSession } from '../api/index.ts'
import AppShell from '../components/AppShell.tsx'
import AuthLayout from '../components/AuthLayout.tsx'
import NotFoundPage from '../pages/NotFoundPage.tsx'
import { LOGIN_PATH, rememberWantedPage } from './wantedPage.ts'

// Route protection. The stored session (#25) decides: a page re-reads it on every
// render, so a login, logout or expiry counts from the next navigation.

/** Pages for logged-in users. Without a session, opens /login and remembers the page. */
export function RequireAuth() {
  const location = useLocation()
  if (getSession() === null) {
    return <Navigate to={LOGIN_PATH} replace state={rememberWantedPage(location)} />
  }
  return <Outlet />
}

/** Login and registration. With a session, opens `/`. */
export function GuestOnly() {
  if (getSession() !== null) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}

/** "Page not found" for everyone: in the app shell when logged in, else without it. */
export function NotFoundRoute() {
  if (getSession() !== null) {
    return (
      <AppShell>
        <NotFoundPage />
      </AppShell>
    )
  }
  return (
    <AuthLayout>
      <NotFoundPage />
    </AuthLayout>
  )
}
