import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { listEntries, listTags, type Category, type Entry } from '../api/index.ts'
import { WAKING_UP_MESSAGE, unexpectedErrorMessage } from '../auth/requestErrors.ts'
import { useWakingUpHint } from '../auth/useWakingUpHint.ts'
import { Button, ButtonLink } from '../components/Button.tsx'
import { focusWhenShown } from '../components/focus.ts'
import { CATEGORIES, categoryClassName } from '../components/categories.ts'
import CategoryChip from '../components/CategoryChip.tsx'
import EmptyState from '../components/EmptyState.tsx'
import { ReviewIllustration } from '../components/Illustrations.tsx'
import EntryRow from '../components/EntryRow.tsx'
import { groupByMonth } from '../components/groupByMonth.ts'
import Message from '../components/Message.tsx'
import { TextField } from '../components/TextField.tsx'
import { LAPTOP_QUERY, useMediaQuery } from '../components/useMediaQuery.ts'
import {
  NO_FILTER,
  entryQuery,
  filterSearchParams,
  filtersInUse,
  parseFilter,
  startAfterEnd,
  toggleCategory,
  type ReviewFilter,
} from '../review/reviewFilter.ts'
import { DATE_ORDER_ERROR, NO_ENTRIES_TEXT, NO_MATCH_TEXT, entryCountText } from '../review/reviewTexts.ts'
import SummaryPanel from '../review/SummaryPanel.tsx'
import TagFilterField, { type TagsLoad } from '../review/TagFilterField.tsx'
import { useDateDraft } from '../review/useDateDraft.ts'
import '../components/categories.css'
import './ReviewPage.css'

/** The result on screen, and the request it answers (the filter's query and the attempt). */
type Shown =
  | { request: string; status: 'loaded'; entries: Entry[]; filtered: boolean }
  | { request: string; status: 'failed'; message: string }

interface CategoryGroup {
  category: Category
  entries: Entry[]
}

/** The entries by category, in the fixed order, keeping the API order inside each (FR-R2). */
function groupByCategory(entries: readonly Entry[]): CategoryGroup[] {
  return CATEGORIES.map((category) => ({
    category,
    entries: entries.filter((entry) => entry.category === category),
  })).filter((group) => group.entries.length > 0)
}

// The review page (FR-R1, FR-R2; design note on #31): filters by period, categories and
// tags, kept in the URL, and the matching entries grouped by category, then by month.
// Results update by themselves whenever the filter changes. The summary panel (FR-R3 to
// FR-R5, #32) drafts a summary of exactly the entries shown.
export default function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.toString()
  // The one filter that drives the controls and the request.
  const filter = useMemo(() => parseFilter(new URLSearchParams(search)), [search])
  const queryKey = filterSearchParams(filter).toString()
  const dateError = startAfterEnd(filter)
  const inUse = filtersInUse(filter)
  const laptop = useMediaQuery(LAPTOP_QUERY)
  const [panelOpen, setPanelOpen] = useState(false)
  // The phone panel is open while the date error shows; the laptop has no panel.
  const panelShown = laptop || panelOpen || dateError
  const [attempt, setAttempt] = useState(0)
  // The request a "Try again" started, so only its failure moves focus (#84).
  const [retried, setRetried] = useState<string | null>(null)
  const [shown, setShown] = useState<Shown | null>(null)
  const [tags, setTags] = useState<TagsLoad>({ status: 'loading' })
  const request = `${queryKey}#${attempt}`
  const loading = !dateError && shown?.request !== request
  const wakingUp = useWakingUpHint(loading)
  // While loading, the previous results stay; after a failure, only the loading line shows.
  const result = !dateError && shown?.status === 'loaded' ? shown : null
  const failure = !dateError && !loading && shown?.status === 'failed' ? shown : null
  // The entries shown for the current filter, or null while they load or after they failed.
  const entryCount = !loading && result !== null ? result.entries.length : null
  const toggleRef = useRef<HTMLButtonElement>(null)
  const firstChipRef = useRef<HTMLDivElement>(null)
  const id = useId()
  const panelId = `${id}-filters`
  const dateErrorId = `${id}-date-error`
  // The date inputs show what the user types at once; the filter (the URL) follows (useDateDraft).
  const [startText, changeStart] = useDateDraft(filter.startDate, (startDate) => updateFilter({ ...filter, startDate }))
  const [endText, changeEnd] = useDateDraft(filter.endDate, (endDate) => updateFilter({ ...filter, endDate }))

  useEffect(() => {
    if (dateError) {
      return undefined
    }
    const current = parseFilter(new URLSearchParams(queryKey))
    const answers = `${queryKey}#${attempt}`
    let active = true
    listEntries(entryQuery(current))
      .then(({ entries }) => {
        if (active) {
          setShown({ request: answers, status: 'loaded', entries, filtered: filtersInUse(current) > 0 })
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setShown({ request: answers, status: 'failed', message: unexpectedErrorMessage(error) })
        }
      })
    return () => {
      // A newer filter replaces this request: its answer changes nothing.
      active = false
    }
  }, [queryKey, attempt, dateError])

  useEffect(() => {
    let active = true
    listTags()
      .then((list) => {
        if (active) {
          setTags({ status: 'loaded', tags: list.tags })
        }
      })
      .catch(() => {
        if (active) {
          setTags({ status: 'failed' })
        }
      })
    return () => {
      active = false
    }
  }, [])

  function updateFilter(next: ReviewFilter) {
    // Fixing the dates keeps the phone panel open, so it does not close under the user.
    if (dateError) {
      setPanelOpen(true)
    }
    setSearchParams(filterSearchParams(next), { replace: true })
  }

  /** Focus for when a control disappears: the first category chip, or the closed panel's toggle. */
  function focusFilters() {
    if (panelShown) {
      firstChipRef.current?.querySelector('button')?.focus()
    } else {
      toggleRef.current?.focus()
    }
  }

  function clearFilters() {
    // The target stays on the page, so it can take focus before the buttons go.
    focusFilters()
    updateFilter(NO_FILTER)
  }

  const clearButton = (
    <Button variant="secondary" onClick={clearFilters}>
      Clear filters
    </Button>
  )

  const filters = (
    <div className="review-page__filters" id={panelId} hidden={!panelShown}>
      <div className="review-page__group">
        <div className="review-page__dates">
          <TextField
            id={`${id}-start`}
            label="Start date"
            type="date"
            value={startText}
            invalid={dateError}
            describedBy={dateError ? dateErrorId : undefined}
            onChange={(event) => changeStart(event.target.value)}
          />
          <TextField
            id={`${id}-end`}
            label="End date"
            type="date"
            value={endText}
            invalid={dateError}
            describedBy={dateError ? dateErrorId : undefined}
            onChange={(event) => changeEnd(event.target.value)}
          />
        </div>
        <div className="field__messages review-page__date-error" id={dateErrorId} role="alert">
          {dateError && <p className="field__message">{DATE_ORDER_ERROR}</p>}
        </div>
      </div>
      <div className="review-page__group" role="group" aria-labelledby={`${id}-categories`}>
        <p className="field__label review-page__label" id={`${id}-categories`}>
          Categories
        </p>
        <div className="review-page__chips" ref={firstChipRef}>
          {CATEGORIES.map((category) => (
            <CategoryChip
              key={category}
              category={category}
              filter
              selected={filter.categories.includes(category)}
              onToggle={() => updateFilter({ ...filter, categories: toggleCategory(filter.categories, category) })}
            />
          ))}
        </div>
      </div>
      <div className="review-page__group review-page__tags">
        <TagFilterField
          id={`${id}-tags`}
          known={tags}
          selected={filter.tags}
          onChange={(next) => updateFilter({ ...filter, tags: next })}
          onFocusElsewhere={focusFilters}
        />
      </div>
      {inUse > 0 && <div className="review-page__group">{clearButton}</div>}
    </div>
  )

  return (
    <section className="page review-page">
      <h1>Review</h1>
      <div className="review-page__layout">
        <div className="review-page__main">
          {!laptop && (
            <Button
              ref={toggleRef}
              className="review-page__toggle"
              variant="secondary"
              aria-expanded={panelShown}
              aria-controls={panelId}
              onClick={() => setPanelOpen(dateError ? true : !panelShown)}
            >
              Filters
              {inUse > 0 && ' '}
              {inUse > 0 && (
                <span className="review-page__count">
                  {inUse}
                  {/* A whitespace text node: it shows nothing in the badge but separates the words. */}
                  {' '}
                  <span className="visually-hidden">in use</span>
                </span>
              )}
            </Button>
          )}
          {filters}
          <div className="review-page__results">
            {loading && (
              <div className="review-page__state">
                <p className="review-page__loading" role="status">
                  <span className="spinner" aria-hidden="true" />
                  Loading entries…
                </p>
                <Message variant="info">{wakingUp ? WAKING_UP_MESSAGE : null}</Message>
              </div>
            )}
            {failure !== null && (
              <div className="review-page__state">
                <Message variant="error">{failure.message}</Message>
                <div>
                  <Button
                    variant="secondary"
                    // After a retry fails again, focus goes to the new button, unless the user
                    // moved on, for example to a filter (#84).
                    ref={failure.request === retried ? focusWhenShown : undefined}
                    onClick={() => {
                      setRetried(`${queryKey}#${attempt + 1}`)
                      setAttempt((count) => count + 1)
                    }}
                  >
                    Try again
                  </Button>
                </div>
              </div>
            )}
            <p className="review-page__total" role="status">
              {result === null ? '' : entryCountText(result.entries.length)}
            </p>
            {result !== null && result.entries.length === 0 && (
              <EmptyState
                illustration={<ReviewIllustration />}
                action={
                  result.filtered ? (
                    clearButton
                  ) : (
                    <ButtonLink variant="secondary" to="/entries/new">
                      New entry
                    </ButtonLink>
                  )
                }
              >
                {result.filtered ? NO_MATCH_TEXT : NO_ENTRIES_TEXT}
              </EmptyState>
            )}
            {result !== null && result.entries.length > 0 && (
              <div className="review-page__groups" aria-busy={loading}>
                {groupByCategory(result.entries).map((group, index) => {
                  const headingId = `${id}-category-${index}`
                  return (
                    <section className="review-page__category" key={group.category} aria-labelledby={headingId}>
                      <h2 id={headingId} className="review-page__category-heading">
                        <span className={`review-page__dot ${categoryClassName(group.category)}`} aria-hidden="true" />
                        <span>{group.category}</span>{' '}
                        <span className="review-page__category-count">{entryCountText(group.entries.length)}</span>
                      </h2>
                      {groupByMonth(group.entries).map((month) => {
                        const monthId = `${headingId}-${month.key}`
                        return (
                          <section className="review-page__month" key={month.key} aria-labelledby={monthId}>
                            <h3 id={monthId}>{month.heading}</h3>
                            <ul className="review-page__list">
                              {month.entries.map((entry) => (
                                <li key={entry.id}>
                                  <EntryRow entry={entry} tags={entry.tags} />
                                </li>
                              ))}
                            </ul>
                          </section>
                        )
                      })}
                    </section>
                  )
                })}
              </div>
            )}
          </div>
        </div>
        <SummaryPanel filter={filter} entryCount={entryCount} />
      </div>
    </section>
  )
}
