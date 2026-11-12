import { Link } from 'react-router'
import './Wordmark.css'

interface WordmarkProps {
  /** In the app shell the wordmark is a link to `/`; elsewhere it is plain text. */
  link?: boolean
}

/** "Winlog" in Bricolage Grotesque 800, plum: 24px on the phone, 30px on the laptop. */
export default function Wordmark({ link = false }: WordmarkProps) {
  if (link) {
    return (
      <Link className="wordmark wordmark--link" to="/">
        Winlog
      </Link>
    )
  }
  return <p className="wordmark">Winlog</p>
}
