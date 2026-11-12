import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router'
import PlaceholderPage from '../components/PlaceholderPage.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import { cameFromEntrySave } from '../entries/entrySavedNotice.ts'
import { ENTRY_SAVED_MESSAGE } from '../entries/entryTexts.ts'
import './EntriesPage.css'

// The entries list comes in #29. After saving an edit, this page shows "Entry saved." at
// the top once (#27).
export default function EntriesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const saved = useSavedMessage()
  const { show } = saved
  const fromSave = cameFromEntrySave(location.state)

  useEffect(() => {
    if (!fromSave) {
      return
    }
    show()
    // Forget it, so a reload or coming back later does not show it again.
    void navigate(location.pathname, { replace: true, state: null })
  }, [fromSave, show, navigate, location.pathname])

  return (
    <PlaceholderPage
      title="Entries"
      notice={
        <SavedMessage phase={saved.phase} count={saved.count}>
          {ENTRY_SAVED_MESSAGE}
        </SavedMessage>
      }
    />
  )
}
