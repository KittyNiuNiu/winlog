import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  NotFoundError,
  ValidationError,
  createEntry,
  updateEntry,
  type Category,
  type Entry,
  type EntryInput,
} from '../api/index.ts'
import { UNEXPECTED_ERROR_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { Button } from '../components/Button.tsx'
import { CATEGORIES } from '../components/categories.ts'
import CategoryChip from '../components/CategoryChip.tsx'
import Message from '../components/Message.tsx'
import { TextArea, TextField } from '../components/TextField.tsx'
import { LAPTOP_QUERY, useMediaQuery } from '../components/useMediaQuery.ts'
import {
  CATEGORY_PROBLEM,
  DATE_PROBLEM,
  ENTRY_GONE_MESSAGE,
  RESULT_PROBLEM,
  TAGS_PROBLEM,
  TEXT_PROBLEM,
} from './entryTexts.ts'
import { isCompleteDate, localToday } from './localDate.ts'
import TagField from './TagField.tsx'
import { addTagNames } from './tagNames.ts'
import { useLeavePrompt } from './useLeavePrompt.tsx'
import './EntryForm.css'

type Field = 'text' | 'category' | 'date' | 'tags' | 'result'

interface FormValues {
  text: string
  category: Category | null
  date: string
  tags: string[]
  result: string
}

/** Each field's message, for the app's own check and for a server error on it. */
const FIELD_PROBLEMS: Record<Field, string> = {
  text: TEXT_PROBLEM,
  category: CATEGORY_PROBLEM,
  date: DATE_PROBLEM,
  tags: TAGS_PROBLEM,
  result: RESULT_PROBLEM,
}

export const RESULT_HINT = 'Optional. What changed because of it?'

function blankValues(): FormValues {
  // Worked out when the form starts, so it is right after midnight too.
  return { text: '', category: null, date: localToday(), tags: [], result: '' }
}

function valuesOf(entry: Entry): FormValues {
  return {
    text: entry.text,
    category: entry.category,
    date: entry.date,
    tags: [...entry.tags],
    result: entry.result_impact ?? '',
  }
}

function sameValues(a: FormValues, b: FormValues): boolean {
  return (
    a.text === b.text &&
    a.category === b.category &&
    a.date === b.date &&
    a.result === b.result &&
    a.tags.length === b.tags.length &&
    a.tags.every((tag, index) => tag === b.tags[index])
  )
}

/** The fields the app checks before saving, in the order they appear on the form (§7.2). */
function problemsOf(values: FormValues): Field[] {
  const problems: Field[] = []
  if (values.text.trim() === '') {
    problems.push('text')
  }
  if (values.category === null) {
    problems.push('category')
  }
  if (!isCompleteDate(values.date)) {
    problems.push('date')
  }
  return problems
}

/** The form field a server validation error names, or null for one not on the form. */
function formFieldOf(name: string): Field | null {
  if (name === 'text' || name === 'date' || name === 'category') {
    return name
  }
  if (name === 'tags' || name.startsWith('tags.')) {
    return 'tags'
  }
  if (name === 'result_impact') {
    return 'result'
  }
  return null
}

interface EntryFormProps {
  /** The entry to edit. Without it, the form creates a new entry. */
  entry?: Entry
  /** The user's existing tags, offered in the tag list. */
  knownTags: readonly string[]
  /** Called once the entry is saved. The page decides what comes next. */
  onSaved: (entry: Entry) => void
  /** Shows a Cancel button (edit page only). */
  onCancel?: () => void
}

/**
 * The entry form (FR-E1 to FR-E4): text, category, date, and tags and result folded under
 * "Add tags and result". Saving never calls the AI (§7.2).
 */
export default function EntryForm({ entry, knownTags, onSaved, onCancel }: EntryFormProps) {
  const isNew = entry === undefined
  const laptop = useMediaQuery(LAPTOP_QUERY)
  const [initial] = useState<FormValues>(() => (entry === undefined ? blankValues() : valuesOf(entry)))
  const [values, setValues] = useState<FormValues>(initial)
  const [tagInput, setTagInput] = useState('')
  const [foldOpen, setFoldOpen] = useState(() => initial.tags.length > 0 || initial.result !== '')
  const [checked, setChecked] = useState(false)
  const [serverProblems, setServerProblems] = useState<Partial<Record<Field, true>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)

  const textRef = useRef<HTMLTextAreaElement>(null)
  const categoryRef = useRef<HTMLDivElement>(null)
  const dateRef = useRef<HTMLInputElement>(null)
  const tagInputRef = useRef<HTMLInputElement>(null)

  const dirty = !sameValues(values, initial) || tagInput !== ''
  const { dialog, allowLeaving } = useLeavePrompt(dirty)

  useEffect(() => {
    if (isNew) {
      // Without scrolling, so the "Entry saved." band at the top stays in view.
      textRef.current?.focus({ preventScroll: true })
    }
  }, [isNew])

  const clientProblems = checked ? problemsOf(values) : []

  function messagesFor(field: Field): string[] {
    return clientProblems.includes(field) || serverProblems[field] === true ? [FIELD_PROBLEMS[field]] : []
  }

  function change<K extends Field>(field: K, value: FormValues[K]) {
    if (savingRef.current) {
      return
    }
    setValues((current) => ({ ...current, [field]: value }))
    setServerProblems((current) => ({ ...current, [field]: undefined }))
  }

  function focusField(field: Field) {
    if (field === 'text') {
      textRef.current?.focus()
    } else if (field === 'category') {
      categoryRef.current?.querySelector('button')?.focus()
    } else if (field === 'date') {
      dateRef.current?.focus()
    }
  }

  function showValidationError(error: ValidationError) {
    const problems: Partial<Record<Field, true>> = {}
    let other = error.fields.length === 0
    for (const { field } of error.fields) {
      const formField = formFieldOf(field)
      if (formField === null) {
        other = true
      } else {
        problems[formField] = true
      }
    }
    setServerProblems(problems)
    if (problems.tags === true || problems.result === true) {
      setFoldOpen(true)
    }
    setFormError(other ? UNEXPECTED_ERROR_MESSAGE : null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (savingRef.current) {
      return
    }
    // Text still in the tag input becomes a tag, so nothing typed is lost.
    const toSave: FormValues = { ...values, tags: addTagNames(values.tags, [tagInput]) }
    if (tagInput !== '') {
      setValues(toSave)
      setTagInput('')
    }
    setChecked(true)
    const [firstProblem] = problemsOf(toSave)
    if (firstProblem !== undefined) {
      focusField(firstProblem)
      return
    }

    const body: EntryInput = {
      text: toSave.text,
      date: toSave.date,
      category: toSave.category as Category,
      tags: toSave.tags,
      // Sent as typed: an empty result is stored as none (#9, #10).
      result_impact: toSave.result,
    }
    savingRef.current = true
    setSaving(true)
    setFormError(null)
    setServerProblems({})
    let saved: Entry
    try {
      saved = entry === undefined ? await createEntry(body) : await updateEntry(entry.id, body)
    } catch (error) {
      savingRef.current = false
      setSaving(false)
      if (error instanceof ValidationError) {
        showValidationError(error)
      } else if (error instanceof NotFoundError && entry !== undefined) {
        setFormError(ENTRY_GONE_MESSAGE)
      } else {
        setFormError(unexpectedErrorMessage(error))
      }
      return
    }
    allowLeaving()
    onSaved(saved)
  }

  const categoryMessages = messagesFor('category')

  return (
    <>
      <form className="entry-form" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <TextArea
          id="entry-text"
          label="What happened?"
          ref={textRef}
          value={values.text}
          readOnly={saving}
          messages={messagesFor('text')}
          onChange={(event) => change('text', event.target.value)}
        />

        <div className="entry-form__section">
          <div className="field__label" id="entry-category-label">
            Category
          </div>
          <div
            ref={categoryRef}
            className="entry-form__chips"
            role="group"
            aria-labelledby="entry-category-label"
            aria-describedby={categoryMessages.length > 0 ? 'entry-category-messages' : undefined}
          >
            {CATEGORIES.map((category) => (
              <CategoryChip
                key={category}
                category={category}
                selected={values.category === category}
                // Tapping the selected chip keeps it selected.
                onToggle={() => change('category', category)}
              />
            ))}
          </div>
          <div className="field__messages" id="entry-category-messages" role="alert">
            {categoryMessages.map((message) => (
              <p className="field__message" key={message}>
                {message}
              </p>
            ))}
          </div>
        </div>

        <div className="entry-form__section">
          <TextField
            id="entry-date"
            label="Date"
            type="date"
            ref={dateRef}
            value={values.date}
            readOnly={saving}
            messages={messagesFor('date')}
            onChange={(event) => change('date', event.target.value)}
          />
        </div>

        <div className="entry-form__section">
          <Button
            variant="secondary"
            className="entry-form__fold"
            aria-expanded={foldOpen}
            aria-controls="entry-more"
            onClick={() => {
              if (!savingRef.current) {
                setFoldOpen((open) => !open)
              }
            }}
          >
            Add tags and result
          </Button>
          <div className="entry-form__more" id="entry-more" hidden={!foldOpen}>
            <TagField
              id="entry-tags"
              tags={values.tags}
              input={tagInput}
              knownTags={knownTags}
              messages={messagesFor('tags')}
              readOnly={saving}
              inputRef={tagInputRef}
              onTagsChange={(tags) => change('tags', tags)}
              onInputChange={(input) => {
                if (!savingRef.current) {
                  setTagInput(input)
                }
              }}
            />
            <div className="entry-form__section">
              <TextArea
                id="entry-result"
                label="Result"
                hint={RESULT_HINT}
                value={values.result}
                readOnly={saving}
                messages={messagesFor('result')}
                onChange={(event) => change('result', event.target.value)}
              />
            </div>
          </div>
        </div>

        <Message variant="error" className="entry-form__error">
          {formError}
        </Message>

        <div className="entry-form__actions">
          <Button
            type="submit"
            variant="primary"
            size={laptop ? 'normal' : 'large'}
            className="entry-form__save"
            busy={saving}
            busyLabel="Saving…"
          >
            Save entry
          </Button>
          {onCancel !== undefined && (
            <Button variant="secondary" className="entry-form__cancel" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </form>
      {dialog}
    </>
  )
}
