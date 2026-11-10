import { Outlet } from 'react-router'
import './AuthLayout.css'

// Layout for login and register: the product name, but no app navigation.
export default function AuthLayout() {
  return (
    <div className="auth">
      <p className="auth__brand">Winlog</p>
      <main className="auth__main">
        <Outlet />
      </main>
    </div>
  )
}
