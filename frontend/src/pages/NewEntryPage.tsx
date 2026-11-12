import { useState } from 'react'
import { useLocation } from 'react-router'
import type { Entry } from '../api/index.ts'
import EntryRow from '../components/EntryRow.tsx'
import SavedMessage from '../components/SavedMessage.tsx'
import { useSavedMessage } from '../components/useSavedMessage.ts'
import EntryForm from '../entries/EntryForm.tsx'
import { ENTRY_SAVED_MESSAGE } from '../entries/entryTexts.ts'
import { useKnownTags } from '../entries/useKnownTags.ts'
import '../entries/EntryForm.css'

// The capture screen (FR-E1 to FR-E3, DESIGN.md → Layout). After saving, the user stays
// here: "Entry saved." at the top, an empty form ready for the next entry, and "Just
// saved" below, which lists the entries saved here during this visit (product owner,
// 2026-11-12). The list lives in the page only and empties when the user leaves or reloads.
export default function NewEntryPage() {
  const location = useLocation()
  const saved = useSavedMessage()
  const [knownTags, addKnownTags] = useKnownTags()
  const [justSaved, setJustSaved] = useState<Entry[]>([])
  const [saveCount, setSaveCount] = useState(0)

  function handleSaved(entry: Entry) {
    // Scroll first: the new form then takes the cursor without scrolling the band away.
    window.scrollTo({ top: 0 })
    saved.show()
    setJustSaved((current) => [entry, ...current])
    addKnownTags(entry.tags)
    setSaveCount((count) => count + 1)
  }

  return (
    <section className="page entry-page">
      <SavedMessage phase={saved.phase} count={saved.count}>
        {ENTRY_SAVED_MESSAGE}
      </SavedMessage>
      <h1>New entry</h1>
      {/* A new form after each save, and after leaving to this page again ("New entry"). */}
      <EntryForm key={`${location.key}-${saveCount}`} knownTags={knownTags} onSaved={handleSaved} />
      {justSaved.length > 0 && (
        <section className="just-saved" aria-labelledby="just-saved-title">
          <h2 id="just-saved-title">Just saved</h2>
          <ul className="just-saved__list">
            {justSaved.map((entry) => (
              <li key={entry.id}>
                <EntryRow entry={entry} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}
