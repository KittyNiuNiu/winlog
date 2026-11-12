import type { ReactNode } from 'react'
import { Outlet } from 'react-router'
import Wordmark from './Wordmark.tsx'
import './AuthLayout.css'

interface AuthLayoutProps {
  /** The page to show. By default, the matching child route. */
  children?: ReactNode
}

// Layout for login, register and, for logged-out visitors, "Page not found": the
// wordmark as plain text, but no app navigation. One column, centred on the laptop.
export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth">
      <div className="auth__column">
        <Wordmark />
        <main className="auth__main">{children ?? <Outlet />}</main>
      </div>
    </div>
  )
}
