import { X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import Icon from '../components/Icon.tsx'
import Message from '../components/Message.tsx'
import { TextField } from '../components/TextField.tsx'
import '../entries/TagField.css'
import { addTagNames, matchingTags } from '../entries/tagNames.ts'
import './TagFilterField.css'

/** The user's tags from `GET /tags` (#8), as the review page loaded them. */
export type TagsLoad = { status: 'loading' } | { status: 'loaded'; tags: string[] } | { status: 'failed' }

export const TAG_FILTER_HINT = 'Shows entries with any of the selected tags'
export const NO_TAGS_TEXT = 'No tags yet.'
export const TAGS_FAILED_TEXT = "Tags couldn't be loaded. Reload the page to try again."

interface TagFilterFieldProps {
  id: string
  known: TagsLoad
  /** The selected tags, in the order they were chosen. */
  selected: readonly string[]
  onChange: (tags: string[]) => void
  /** Moves focus somewhere sensible after the last tag is removed and there is no search field. */
  onFocusElsewhere: () => void
}

/**
 * The review page's tag filter (design note on #31): a search field that offers the
 * user's tags whose names contain the typed text, and the selected tags as chips with a
 * remove button. It looks like the entry form's tag field, but only offered tags can be
 * chosen (typed text alone selects nothing), and its hint sits under the input. Typing
 * changes nothing outside this field.
 */
export default function TagFilterField({ id, known, selected, onChange, onFocusElsewhere }: TagFilterFieldProps) {
  const [input, setInput] = useState('')
  const [listOpen, setListOpen] = useState(false)
  const [highlight, setHighlight] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  const hasField = known.status === 'loading' || (known.status === 'loaded' && known.tags.length > 0)
  // Whether the search field had focus, so focus is not lost when the field is replaced.
  const fieldHadFocus = useRef(false)
  const listId = `${id}-list`
  const hintId = `${id}-hint`
  const offered = known.status === 'loaded' ? matchingTags(known.tags, selected, input) : []
  const expanded = listOpen && offered.length > 0
  const active = expanded && highlight < offered.length ? highlight : -1
  const optionId = (index: number) => `${id}-option-${index}`

  // The tag list arrived empty or failed while the search field had focus.
  useEffect(() => {
    if (!hasField && fieldHadFocus.current) {
      fieldHadFocus.current = false
      onFocusElsewhere()
    }
  }, [hasField, onFocusElsewhere])

  function closeList() {
    setListOpen(false)
    setHighlight(-1)
  }

  function choose(name: string) {
    onChange(addTagNames(selected, [name]))
    setInput('')
    closeList()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        if (offered.length === 0) {
          return
        }
        event.preventDefault()
        setListOpen(true)
        setHighlight(expanded ? (active + 1) % offered.length : 0)
        return
      case 'ArrowUp':
        if (!expanded) {
          return
        }
        event.preventDefault()
        setHighlight(active <= 0 ? offered.length - 1 : active - 1)
        return
      case 'Enter': {
        // Only a highlighted offered tag can be chosen; typed text alone selects nothing.
        const chosen = active >= 0 ? offered[active] : undefined
        if (chosen !== undefined) {
          event.preventDefault()
          choose(chosen)
        }
        return
      }
      case 'Escape':
        if (expanded) {
          event.preventDefault()
          closeList()
        }
        return
      default:
    }
  }

  function remove(tag: string) {
    const index = selected.indexOf(tag)
    const rest = selected.filter((existing) => existing !== tag)
    onChange(rest)
    if (hasField) {
      inputRef.current?.focus()
      return
    }
    // No search field: the chip that takes its place, the one before it, or elsewhere.
    // That element is already on the page, so it can take focus now.
    const next = rest[Math.min(index, rest.length - 1)]
    const button = next === undefined ? undefined : removeButtons.current.get(next)
    if (button === undefined) {
      onFocusElsewhere()
    } else {
      button.focus()
    }
  }

  const list = (
    <ul className="tag-list" id={listId} role="listbox" aria-label="Matching tags" hidden={!expanded}>
      {expanded &&
        offered.map((name, index) => (
          <li
            key={name}
            id={optionId(index)}
            className={`tag-list__option${index === active ? ' tag-list__option--active' : ''}`}
            role="option"
            aria-selected={index === active}
            // Keep the cursor in the input, so choosing does not close the list first.
            onMouseDown={(event) => event.preventDefault()}
            onPointerMove={() => setHighlight(index)}
            onClick={() => choose(name)}
          >
            {name}
          </li>
        ))}
    </ul>
  )

  return (
    <div className="tag-field tag-filter">
      {hasField ? (
        <>
          <TextField
            id={id}
            label="Tags"
            describedBy={hintId}
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? optionId(active) : undefined}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            value={input}
            onChange={(event) => {
              setInput(event.target.value)
              setHighlight(-1)
              setListOpen(true)
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              fieldHadFocus.current = true
            }}
            onBlur={(event) => {
              closeList()
              // A field that is removed loses focus to nowhere; keep the flag then.
              if (event.relatedTarget !== null) {
                fieldHadFocus.current = false
              }
            }}
            after={list}
          />
          <p className="field__hint tag-filter__hint" id={hintId}>
            {TAG_FILTER_HINT}
          </p>
        </>
      ) : (
        <>
          <p className="field__label tag-filter__label" id={`${id}-label`}>
            Tags
          </p>
          {known.status === 'failed' ? (
            <Message className="tag-filter__note" variant="error">
              {TAGS_FAILED_TEXT}
            </Message>
          ) : (
            <p className="tag-filter__note tag-filter__none">{NO_TAGS_TEXT}</p>
          )}
        </>
      )}
      {selected.length > 0 && (
        <ul className="tag-chips" aria-label="Selected tags">
          {selected.map((tag) => (
            <li key={tag} className="tag-chip">
              <span className="tag-chip__label">{tag}</span>
              <button
                ref={(element) => {
                  if (element === null) {
                    removeButtons.current.delete(tag)
                  } else {
                    removeButtons.current.set(tag, element)
                  }
                }}
                type="button"
                className="tag-chip__remove"
                aria-label={`Remove ${tag}`}
                onClick={() => remove(tag)}
              >
                <Icon icon={X} size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
