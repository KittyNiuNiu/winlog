import type { ReactNode } from 'react'
import { Outlet } from 'react-router'
import './AuthLayout.css'

interface AuthLayoutProps {
  /** The page to show. By default, the matching child route. */
  children?: ReactNode
}

// Layout for login, register and, for logged-out visitors, "Page not found": the product
// name, but no app navigation.
export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth">
      <p className="auth__brand">Winlog</p>
      <main className="auth__main">{children ?? <Outlet />}</main>
    </div>
  )
}
