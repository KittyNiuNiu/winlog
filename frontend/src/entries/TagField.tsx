import { Sparkles, X } from 'lucide-react'
import { useState, type ClipboardEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react'
import Icon from '../components/Icon.tsx'
import { TextField } from '../components/TextField.tsx'
import { SUGGESTED_MARK } from './suggestions.ts'
import { addTagNamesWithin, joinTagNames, matchingTags, type TagLimitProblems } from './tagNames.ts'
import './TagField.css'

interface TagFieldProps {
  id: string
  /** The added tags, in the order they were added. */
  tags: readonly string[]
  /** The added tags that an AI suggestion put there, shown marked "Suggested". */
  suggested?: readonly string[]
  /** The text in the tag input that is not a tag yet. */
  input: string
  /** The user's existing tags, offered in the list. */
  knownTags: readonly string[]
  messages: ReactNode[]
  /** While saving: nothing can be changed, but the field keeps its normal look. */
  readOnly: boolean
  inputRef: RefObject<HTMLInputElement | null>
  /** The new tags, and the names the user typed or chose (none when a tag was removed). */
  onTagsChange: (tags: string[], typed: readonly string[]) => void
  onInputChange: (input: string) => void
  /** Names were not added because they broke a tag limit (#43); they stay in the input. */
  onTagLimit?: (problems: TagLimitProblems) => void
}

export const TAGS_HINT = 'Optional. Press Enter or type a comma to add a tag.'

/**
 * The tag field: a combobox that offers the user's existing tags whose names contain the
 * typed text, and the added tags as chips with a remove button. Enter or a comma adds the
 * typed text; choosing an offered tag adds it with its stored spelling. Names over 40
 * characters, or beyond 10 tags, are not added (#43): they stay in the input, joined with
 * ", ", and `onTagLimit` says which limit they broke.
 */
export default function TagField({
  id,
  tags,
  suggested = [],
  input,
  knownTags,
  messages,
  readOnly,
  inputRef,
  onTagsChange,
  onInputChange,
  onTagLimit,
}: TagFieldProps) {
  const [listOpen, setListOpen] = useState(false)
  const [highlight, setHighlight] = useState(-1)
  const listId = `${id}-list`
  const suggestions = matchingTags(knownTags, tags, input)
  const expanded = listOpen && !readOnly && suggestions.length > 0
  const active = expanded && highlight < suggestions.length ? highlight : -1
  const optionId = (index: number) => `${id}-option-${index}`

  function closeList() {
    setListOpen(false)
    setHighlight(-1)
  }

  /** Adds the names that fit and reports the others. Returns the names that did not fit. */
  function addWithin(names: readonly string[]): string[] {
    const result = addTagNamesWithin(tags, names)
    onTagsChange(result.tags, names)
    if (result.rejected.length > 0) {
      onTagLimit?.(result.problems)
    }
    return result.rejected
  }

  function add(names: readonly string[]) {
    onInputChange(joinTagNames(addWithin(names)))
    closeList()
  }

  function handleChange(value: string) {
    if (readOnly) {
      return
    }
    setHighlight(-1)
    if (!value.includes(',')) {
      onInputChange(value)
      setListOpen(true)
      return
    }
    // A typed comma ends a tag; what follows it stays in the input.
    const parts = value.split(',')
    const rest = parts.pop() ?? ''
    const rejected = addWithin(parts)
    onInputChange(rejected.length === 0 ? rest : joinTagNames(rest.trim() === '' ? rejected : [...rejected, rest]))
    setListOpen(rejected.length === 0 && rest.trim() !== '')
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData('text')
    if (!pasted.includes(',')) {
      return
    }
    // Pasting "a, b" adds both tags.
    event.preventDefault()
    if (readOnly) {
      return
    }
    const { selectionStart, selectionEnd } = event.currentTarget
    const start = selectionStart ?? input.length
    const end = selectionEnd ?? input.length
    add(`${input.slice(0, start)}${pasted}${input.slice(end)}`.split(','))
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        if (readOnly || suggestions.length === 0) {
          return
        }
        event.preventDefault()
        setListOpen(true)
        setHighlight(expanded ? (active + 1) % suggestions.length : 0)
        return
      case 'ArrowUp':
        if (!expanded) {
          return
        }
        event.preventDefault()
        setHighlight(active <= 0 ? suggestions.length - 1 : active - 1)
        return
      case 'Enter': {
        // Enter in the tag input never saves the form.
        event.preventDefault()
        if (readOnly) {
          return
        }
        const chosen = active >= 0 ? suggestions[active] : undefined
        // A comma in the input only comes from names that did not fit, joined with ", ".
        add(chosen === undefined ? input.split(',') : [chosen])
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
    if (readOnly) {
      return
    }
    onTagsChange(
      tags.filter((existing) => existing !== tag),
      [],
    )
    inputRef.current?.focus()
  }

  const list = (
    <ul className="tag-list" id={listId} role="listbox" aria-label="Matching tags" hidden={!expanded}>
      {expanded &&
        suggestions.map((name, index) => (
          <li
            key={name}
            id={optionId(index)}
            className={`tag-list__option${index === active ? ' tag-list__option--active' : ''}`}
            role="option"
            aria-selected={index === active}
            // Keep the cursor in the input, so choosing does not close the list first.
            onMouseDown={(event) => event.preventDefault()}
            onPointerMove={() => setHighlight(index)}
            onClick={() => add([name])}
          >
            {name}
          </li>
        ))}
    </ul>
  )

  return (
    <div className="tag-field">
      <TextField
        id={id}
        label="Tags"
        hint={TAGS_HINT}
        messages={messages}
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
        enterKeyHint="enter"
        readOnly={readOnly}
        value={input}
        onChange={(event) => handleChange(event.target.value)}
        onPaste={handlePaste}
        onKeyDown={handleKeyDown}
        onBlur={closeList}
        after={list}
      />
      {tags.length > 0 && (
        <ul className="tag-chips" aria-label="Added tags">
          {tags.map((tag) => {
            const isSuggested = suggested.includes(tag)
            return (
              <li key={tag} className={isSuggested ? 'tag-chip tag-chip--suggested' : 'tag-chip'}>
                <span className="tag-chip__label">{tag}</span>
                {isSuggested && (
                  <>
                    <span className="visually-hidden">, suggested</span>
                    <span className="tag-chip__mark" aria-hidden="true">
                      <Icon icon={Sparkles} size={16} />
                      {SUGGESTED_MARK}
                    </span>
                  </>
                )}
                <button
                  type="button"
                  className="tag-chip__remove"
                  aria-label={`Remove ${tag}`}
                  onClick={() => remove(tag)}
                >
                  <Icon icon={X} size={16} />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
