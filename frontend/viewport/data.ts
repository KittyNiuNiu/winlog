import type { Entry, Summary } from './mockApi.ts'

// Test data for the viewport tests. Today is 13 November 2026 (settings.ts). The long
// content (#36) is here: a 40-character tag name (the maximum), an entry with ten tags (the
// maximum), and a word of more than 60 characters without spaces in an entry and a summary.

/** 40 characters, the longest tag name the API accepts. */
export const LONG_TAG = 'internal-developer-platform-availability'

/** A URL of more than 60 characters without spaces. */
export const LONG_URL = 'https://docs.example.com/engineering/platform/migrations/billing-service-cutover-runbook-v2'

export const TEN_TAGS = [
  LONG_TAG,
  'billing',
  'migration',
  'leadership',
  'mentoring',
  'accessibility',
  'onboarding',
  'presentation',
  'customer-support',
  'quarterly-goals',
]

let counter = 0

function entry(fields: Pick<Entry, 'date' | 'text' | 'category'> & Partial<Entry>): Entry {
  counter += 1
  const id = `00000000-0000-4000-8000-${String(counter).padStart(12, '0')}`
  const created = `${fields.date}T09:00:00Z`
  return { id, tags: [], result_impact: null, created_at: created, updated_at: created, ...fields }
}

/** The entry with the long content, in October. */
export const LONG_ENTRY = entry({
  date: '2026-10-21',
  category: 'Achievement',
  text: `Led the cut-over of the billing service to the new platform without downtime. The runbook is at ${LONG_URL} for the next team.`,
  tags: TEN_TAGS,
  result_impact: 'No failed payments during the switch, and the old cluster was shut down two weeks early.',
})

/** Entries in October and November, the newest on 2 November: older than 7 days, so the nudge shows. */
export const ENTRIES_WITH_NUDGE: Entry[] = [
  entry({
    date: '2026-11-02',
    category: 'Learning',
    text: 'Finished the course on writing accessible forms and used it to fix the error messages on the sign-up page.',
    tags: ['accessibility'],
  }),
  entry({
    date: '2026-11-02',
    category: 'Feedback',
    text: 'My manager said the planning document for Q1 was the clearest one she had read this year.',
    tags: ['leadership', 'quarterly-goals'],
  }),
  LONG_ENTRY,
  entry({
    date: '2026-10-08',
    category: 'Side project',
    text: 'Published the first version of my recipe planner and got twelve users in the first week.',
    tags: ['onboarding'],
  }),
]

/** The same, plus an entry yesterday, so the nudge does not show. */
export const ENTRIES_WITHOUT_NUDGE: Entry[] = [
  entry({
    date: '2026-11-12',
    category: 'Achievement',
    text: 'Shipped the new onboarding flow; setup time for new teams went from two days to one.',
    tags: ['onboarding', 'leadership'],
    result_impact: 'Setup time halved.',
  }),
  ...ENTRIES_WITH_NUDGE,
]

/** The entry the edit page opens. */
export const EDIT_ENTRY = LONG_ENTRY

function summary(fields: Pick<Summary, 'text' | 'filter'> & { created: string }, index: number): Summary {
  const created = `${fields.created}T15:30:00Z`
  return {
    id: `00000000-0000-4000-9000-${String(index).padStart(12, '0')}`,
    text: fields.text,
    filter: fields.filter,
    created_at: created,
    updated_at: created,
  }
}

export const SUMMARIES: Summary[] = [
  summary(
    {
      created: '2026-11-10',
      filter: {
        period_start: '2026-09-01',
        period_end: '2026-11-10',
        categories: ['Achievement', 'Feedback'],
        tags: [LONG_TAG, 'billing', 'migration', 'leadership', 'accessibility'],
      },
      text: `In the autumn you led the billing migration without downtime and documented it in ${LONG_URL}. Your manager praised the clarity of your planning, and the platform team now uses your runbook as its template for every cut-over.`,
    },
    1,
  ),
  summary(
    {
      created: '2026-07-01',
      filter: { period_start: '2026-01-01', period_end: '2026-06-30' },
      text: 'In the first half of the year you onboarded three new teams, mentored two colleagues and presented the accessibility audit.',
    },
    2,
  ),
  summary(
    {
      created: '2025-12-20',
      filter: { period_start: '2025-01-01', period_end: '2025-12-20', categories: ['Learning'] },
      text: 'You finished two courses and turned what you learned into a shared checklist for the team.',
    },
    3,
  ),
]

/** The summary the summary page opens: the one with the long word and several tags. */
export const LONG_SUMMARY = SUMMARIES[0]

/** An id that is in no list, for the missing entry and summary. */
export const MISSING_ID = '00000000-0000-4000-8000-999999999999'
