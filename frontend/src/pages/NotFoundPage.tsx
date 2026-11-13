import { Link } from 'react-router'
import './NotFoundPage.css'

export default function NotFoundPage() {
  return (
    <section className="page">
      <h1>Page not found</h1>
      <p>The page you are looking for does not exist.</p>
      <p>
        <Link className="not-found__link" to="/">
          Go to your entries
        </Link>
      </p>
    </section>
  )
}
