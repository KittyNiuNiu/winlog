import { Sparkles } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  NotAuthenticatedError,
  NotFoundError,
  ValidationError,
  createEntry,
  suggestCategoryAndTags,
  updateEntry,
  type Category,
  type Entry,
  type EntryInput,
  type Suggestion,
} from '../api/index.ts'
import { UNEXPECTED_ERROR_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { Button } from '../components/Button.tsx'
import { CATEGORIES } from '../components/categories.ts'
import CategoryChip from '../components/CategoryChip.tsx'
import Icon from '../components/Icon.tsx'
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
import {
  DISCARD_SUGGESTIONS_LABEL,
  NO_MARKS,
  SUGGESTING_LABEL,
  SUGGEST_LABEL,
  applySuggestion,
  discardSuggestions,
  hasSuggestions,
  marksAfterCategoryChoice,
  marksAfterTagChange,
  suggestedCategoryHint,
  suggestionNoticeOf,
  type Marks,
} from './suggestions.ts'
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

interface FormState {
  values: FormValues
  /** What AI suggestions put in the form and the user has not made their own (#28). */
  marks: Marks
  /** Whether "Add tags and result" is open. */
  foldOpen: boolean
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
 * "Add tags and result". Saving never calls the AI (§7.2). "Suggest category and tags"
 * asks the AI for a category and tags (FR-S1 to FR-S3); they fill only what is empty, stay
 * marked "Suggested" until the user makes them their own, and are saved only with Save
 * entry.
 */
export default function EntryForm({ entry, knownTags, onSaved, onCancel }: EntryFormProps) {
  const isNew = entry === undefined
  const laptop = useMediaQuery(LAPTOP_QUERY)
  const [initial] = useState<FormValues>(() => (entry === undefined ? blankValues() : valuesOf(entry)))
  const [form, setForm] = useState<FormState>(() => ({
    values: initial,
    marks: NO_MARKS,
    foldOpen: initial.tags.length > 0 || initial.result !== '',
  }))
  const { values, marks, foldOpen } = form
  const [tagInput, setTagInput] = useState('')
  const [checked, setChecked] = useState(false)
  const [serverProblems, setServerProblems] = useState<Partial<Record<Field, true>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [suggesting, setSuggesting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const suggestingRef = useRef(false)
  /** Counts suggestion requests; an answer whose number is no longer current is dropped. */
  const requestRef = useRef(0)
  /** Whether focus goes back to the suggest button when the running request ends. */
  const refocusRef = useRef(false)

  const textRef = useRef<HTMLTextAreaElement>(null)
  const categoryRef = useRef<HTMLDivElement>(null)
  const dateRef = useRef<HTMLInputElement>(null)
  const tagInputRef = useRef<HTMLInputElement>(null)
  const suggestRef = useRef<HTMLButtonElement>(null)

  const dirty = !sameValues(values, initial) || tagInput !== ''
  const { dialog, allowLeaving } = useLeavePrompt(dirty)

  useEffect(() => {
    if (isNew) {
      // Without scrolling, so the "Entry saved." band at the top stays in view.
      textRef.current?.focus({ preventScroll: true })
    }
  }, [isNew])

  useEffect(() => {
    const requests = requestRef
    // An answer that arrives after the form is gone changes nothing.
    return () => {
      requests.current += 1
    }
  }, [])

  useEffect(() => {
    if (suggesting || !refocusRef.current) {
      return
    }
    refocusRef.current = false
    // A disabled button loses focus. Bring it back, unless the user has moved on.
    const active = document.activeElement
    if (active === null || active === document.body || active === suggestRef.current) {
      suggestRef.current?.focus()
    }
  }, [suggesting])

  const clientProblems = checked ? problemsOf(values) : []

  function messagesFor(field: Field): string[] {
    return clientProblems.includes(field) || serverProblems[field] === true ? [FIELD_PROBLEMS[field]] : []
  }

  function change<K extends 'text' | 'date' | 'result'>(field: K, value: FormValues[K]) {
    if (savingRef.current) {
      return
    }
    setForm((current) => ({ ...current, values: { ...current.values, [field]: value } }))
    setServerProblems((current) => ({ ...current, [field]: undefined }))
  }

  /** A chip or the hint: the category becomes the user's own choice. */
  function chooseCategory(category: Category) {
    if (savingRef.current) {
      return
    }
    setForm((current) => ({
      ...current,
      values: { ...current.values, category },
      marks: marksAfterCategoryChoice(current.marks, category),
    }))
    setServerProblems((current) => ({ ...current, category: undefined }))
  }

  function changeTags(tags: string[], typed: readonly string[]) {
    if (savingRef.current) {
      return
    }
    setForm((current) => ({
      ...current,
      values: { ...current.values, tags },
      marks: marksAfterTagChange(current.marks, tags, typed),
    }))
    setServerProblems((current) => ({ ...current, tags: undefined }))
  }

  /** Drops the answer of a running suggestion request, if there is one. */
  function dropSuggestionRequest() {
    requestRef.current += 1
    suggestingRef.current = false
    refocusRef.current = false
    setSuggesting(false)
  }

  async function handleSuggest() {
    if (suggestingRef.current || savingRef.current || values.text.trim() === '') {
      return
    }
    requestRef.current += 1
    const request = requestRef.current
    suggestingRef.current = true
    refocusRef.current = document.activeElement === suggestRef.current
    setSuggesting(true)
    setNotice(null)
    let suggestion: Suggestion
    try {
      // Only the text: the AI gets nothing else (AGENTS.md).
      suggestion = await suggestCategoryAndTags({ text: values.text })
    } catch (error) {
      if (requestRef.current !== request) {
        return
      }
      suggestingRef.current = false
      setSuggesting(false)
      // An expired login already went to the login page (#25).
      if (!(error instanceof NotAuthenticatedError)) {
        setNotice(suggestionNoticeOf(error))
      }
      return
    }
    if (requestRef.current !== request) {
      return
    }
    suggestingRef.current = false
    setSuggesting(false)
    // Applied to the form as it is now, not as it was when the button was pressed.
    setForm((current) => {
      const applied = applySuggestion(current, suggestion)
      return {
        values: applied.values,
        marks: applied.marks,
        // New tags must be visible; the cursor stays where it is.
        foldOpen: current.foldOpen || applied.addedTags,
      }
    })
  }

  function handleDiscardSuggestions() {
    if (savingRef.current) {
      return
    }
    setForm((current) => ({ ...current, ...discardSuggestions(current) }))
    // "Discard suggestions" disappears, so focus moves to the suggest button.
    const button = suggestRef.current
    if (button !== null && !button.disabled) {
      button.focus()
    } else {
      textRef.current?.focus()
    }
  }

  function handleApplyHint(category: Category) {
    if (savingRef.current) {
      return
    }
    chooseCategory(category)
    // The hint disappears, so focus moves to the chip it selected.
    categoryRef.current?.querySelectorAll('button')[CATEGORIES.indexOf(category)]?.focus()
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
      setForm((current) => ({ ...current, foldOpen: true }))
    }
    setFormError(other ? UNEXPECTED_ERROR_MESSAGE : null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (savingRef.current) {
      return
    }
    // A suggestion answer after this changes nothing, and the notice goes.
    dropSuggestionRequest()
    setNotice(null)
    // Text still in the tag input becomes a tag, so nothing typed is lost.
    const toSave: FormValues = { ...values, tags: addTagNames(values.tags, [tagInput]) }
    if (tagInput !== '') {
      setForm((current) => ({
        ...current,
        values: toSave,
        marks: marksAfterTagChange(current.marks, toSave.tags, [tagInput]),
      }))
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
  const hint = marks.hint !== null && marks.hint !== values.category ? marks.hint : null

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

        <div className="entry-form__suggest">
          <div className="entry-form__suggest-row">
            <Button
              variant="secondary"
              className="entry-form__suggest-button"
              ref={suggestRef}
              disabled={values.text.trim() === '' || saving}
              busy={suggesting}
              busyLabel={SUGGESTING_LABEL}
              onClick={() => void handleSuggest()}
            >
              <Icon icon={Sparkles} size={20} />
              {SUGGEST_LABEL}
            </Button>
            {hasSuggestions(marks) && (
              <button type="button" className="quiet-action" onClick={handleDiscardSuggestions}>
                {DISCARD_SUGGESTIONS_LABEL}
              </button>
            )}
          </div>
          <Message variant="info" className="entry-form__notice">
            {notice}
          </Message>
        </div>

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
                suggested={values.category === category && marks.category === category}
                // Tapping the selected chip keeps it selected.
                onToggle={() => chooseCategory(category)}
              />
            ))}
          </div>
          {hint !== null && (
            <div className="entry-form__hint">
              <button type="button" className="quiet-action" onClick={() => handleApplyHint(hint)}>
                <Icon icon={Sparkles} size={16} />
                {suggestedCategoryHint(hint)}
              </button>
            </div>
          )}
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
                setForm((current) => ({ ...current, foldOpen: !current.foldOpen }))
              }
            }}
          >
            Add tags and result
          </Button>
          <div className="entry-form__more" id="entry-more" hidden={!foldOpen}>
            <TagField
              id="entry-tags"
              tags={values.tags}
              suggested={marks.tags}
              input={tagInput}
              knownTags={knownTags}
              messages={messagesFor('tags')}
              readOnly={saving}
              inputRef={tagInputRef}
              onTagsChange={changeTags}
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
