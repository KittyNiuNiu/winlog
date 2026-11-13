import { useState } from 'react'
import { dateOrNull } from './reviewFilter.ts'

interface Draft {
  /** What the date input shows: the browser's value, `''` for an empty or incomplete date. */
  text: string
  /** The filter's date when `text` was last matched with it. */
  basis: string | null
  /** Dates this input sent to the filter that the filter has not shown yet, oldest first. */
  sent: (string | null)[]
}

/**
 * The value of a date input whose date lives in the filter (the URL), and the change that
 * sends it there (#31).
 *
 * The router applies a URL change in a transition, after the input event. A date input
 * whose value came straight from the URL would get its old value written back in between,
 * and Chrome then drops the segments being typed: a date typed key by key never arrives.
 * So the input shows its own value, set in the same event. When the filter's date changes
 * to one this input sent, the input stays as it is; any other change (for example "Clear
 * filters", Back or Forward) replaces what the input shows.
 */
export function useDateDraft(
  committed: string | null,
  commit: (date: string | null) => void,
): [string, (text: string) => void] {
  const [draft, setDraft] = useState<Draft>({ text: committed ?? '', basis: committed, sent: [] })
  let current = draft
  if (draft.basis !== committed) {
    const index = draft.sent.indexOf(committed)
    current =
      index >= 0
        ? { text: draft.text, basis: committed, sent: draft.sent.slice(index + 1) }
        : { text: committed ?? '', basis: committed, sent: [] }
    // Adjusting state while rendering: React renders again before it touches the input.
    setDraft(current)
  }

  function change(text: string) {
    const date = dateOrNull(text)
    setDraft((previous) => {
      const last = previous.sent.length > 0 ? previous.sent[previous.sent.length - 1] : previous.basis
      // A date the filter already has (or is about to get) changes nothing in the URL.
      return { ...previous, text, sent: date === last ? previous.sent : [...previous.sent, date] }
    })
    commit(date)
  }

  return [current.text, change]
}
