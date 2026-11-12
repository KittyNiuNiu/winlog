import { useCallback, useEffect, useState } from 'react'
import { listTags } from '../api/index.ts'
import { mergeKnownTags } from './tagNames.ts'

/**
 * The user's existing tags for the tag list (`GET /tags`, #8), loaded once per page, and
 * a function that adds the tags of a just-saved entry without a new request. If loading
 * fails, the list stays empty and nothing is shown: tags can still be typed freely.
 */
export function useKnownTags(): [string[], (names: readonly string[]) => void] {
  const [known, setKnown] = useState<string[]>([])

  useEffect(() => {
    let active = true
    listTags()
      .then(({ tags }) => {
        if (active) {
          setKnown((current) => mergeKnownTags(tags, current))
        }
      })
      .catch(() => {
        // No message: the form works without the list.
      })
    return () => {
      active = false
    }
  }, [])

  const add = useCallback((names: readonly string[]) => {
    setKnown((current) => mergeKnownTags(current, names))
  }, [])

  return [known, add]
}
