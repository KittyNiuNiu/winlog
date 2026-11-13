import { useEffect, useState, type ReactNode } from 'react'
import type { Category, Entry } from '../../api/index.ts'
import { Button } from '../../components/Button.tsx'
import { CATEGORIES } from '../../components/categories.ts'
import CategoryChip from '../../components/CategoryChip.tsx'
import CategoryLabel from '../../components/CategoryLabel.tsx'
import EmptyState from '../../components/EmptyState.tsx'
import EntryRow from '../../components/EntryRow.tsx'
import { EntriesIllustration, LoginIllustration, ReviewIllustration } from '../../components/Illustrations.tsx'
import Message from '../../components/Message.tsx'
import SavedMessage from '../../components/SavedMessage.tsx'
import { TextArea, TextField } from '../../components/TextField.tsx'
import { useSavedMessage } from '../../components/useSavedMessage.ts'
import Wordmark from '../../components/Wordmark.tsx'
import './ComponentPreviewPage.css'

// Development only (`npm run dev`, routes.tsx): every shared component in each of its
// states, for QA and the designer. No login, no app shell, and no link to it in the app.

type PreviewEntry = Pick<Entry, 'date' | 'category' | 'text' | 'result_impact'>

const PASSWORD_HINT = 'At least 10 characters, including an uppercase letter, a number and a special character.'
const EMPTY_STATE_TEXT = 'No entries yet. One sentence about something that went well is enough to start.'

const SAMPLE_ENTRIES: PreviewEntry[] = [
  {
    date: '2026-11-10',
    category: 'Achievement',
    text: 'Shipped the new onboarding checklist two days early. Setup questions in the support channel dropped in the first week.',
    result_impact: 'Setup tickets went from 14 to 5 a week.',
  },
  {
    date: '2026-11-07',
    category: 'Feedback',
    text: "Priya said my sprint review demo was the clearest one this quarter, because I started with the customer's problem.",
    result_impact: null,
  },
  {
    date: '2026-11-05',
    category: 'Learning',
    text: 'Gelernt, wie wir Datenbankmigrationen ohne Ausfallzeit planen: zuerst die neue Spalte anlegen, dann die Daten kopieren und erst danach die alte Spalte löschen.',
    result_impact: null,
  },
  {
    date: '2026-11-02',
    category: 'Side project',
    text: '週末に家計簿アプリの試作版を作り、友人3人に使ってもらった。',
    result_impact: '3人とも、これからも使いたいと言ってくれた。',
  },
  {
    date: '2026-09-30',
    category: 'Achievement',
    text: [
      'Led the incident review for the checkout outage.',
      'Wrote the timeline, ran the meeting and agreed three follow-ups with the payments team.',
      'Notes: https://wiki.example.com/incidents/2026-09-29-checkout-outage-review-and-follow-up-actions',
    ].join('\n'),
    result_impact: 'Two of the three follow-ups were done within a week.',
  },
]

// Entry rows with the entries page's extras (#29). No result, so the plain rows above stay
// the only ones with "Result: …".
const TAGGED_ENTRY: PreviewEntry = {
  date: '2026-11-11',
  category: 'Achievement',
  text: 'Paired with two new joiners on their first pull requests.',
  result_impact: null,
}

const LONG_TAGS_ENTRY: PreviewEntry = {
  date: '2026-11-09',
  category: 'Learning',
  text: 'Read the whole Postgres documentation chapter on transaction isolation.',
  result_impact: null,
}

const LONG_TAGS = ['database-transaction-isolation-levels-and-locking', 'Weiterbildungsveranstaltungsreihe', 'sql']

const ACTIONS_ENTRY: PreviewEntry = {
  date: '2026-11-04',
  category: 'Side project',
  text: 'Fixed the flaky export test in my open source library and wrote down why it failed.',
  result_impact: null,
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="preview__section">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function Sample({ caption, row = false, children }: { caption: string; row?: boolean; children: ReactNode }) {
  return (
    <figure className="preview__sample">
      <figcaption className="preview__caption">{caption}</figcaption>
      <div className={row ? 'preview__row' : undefined}>{children}</div>
    </figure>
  )
}

function ChipSample({ caption, initial, filter = false }: { caption: string; initial: Category[]; filter?: boolean }) {
  const [selected, setSelected] = useState<Category[]>(initial)
  function toggle(category: Category) {
    setSelected((current) =>
      current.includes(category) ? current.filter((item) => item !== category) : [...current, category],
    )
  }
  return (
    <Sample caption={caption} row>
      {CATEGORIES.map((category) => (
        <CategoryChip
          key={category}
          category={category}
          selected={selected.includes(category)}
          onToggle={() => toggle(category)}
          filter={filter}
        />
      ))}
    </Sample>
  )
}

export default function ComponentPreviewPage() {
  const saved = useSavedMessage()
  const { show: showSaved } = saved

  // The saved message shows when the page opens.
  useEffect(() => {
    showSaved()
  }, [showSaved])

  return (
    <main className="preview">
      <h1>Component preview</h1>
      <p>Every shared component in each of its states. This page exists only in development.</p>

      <Section title="Wordmark">
        <Sample caption="24px on the phone, 30px on the laptop">
          <Wordmark />
        </Sample>
      </Section>

      <Section title="Buttons">
        <Sample caption="Primary" row>
          <Button>Log in</Button>
        </Sample>
        <Sample caption="Primary, disabled" row>
          <Button disabled>Log in</Button>
        </Sample>
        <Sample caption="Primary, busy" row>
          <Button busy busyLabel="Logging in…">
            Log in
          </Button>
        </Sample>
        <Sample caption="Primary, large" row>
          <Button size="large">Save entry</Button>
        </Sample>
        <Sample caption="Secondary" row>
          <Button variant="secondary">Draft again</Button>
        </Sample>
        <Sample caption="Secondary, disabled" row>
          <Button variant="secondary" disabled>
            Draft again
          </Button>
        </Sample>
        <Sample caption="Secondary, busy" row>
          <Button variant="secondary" busy busyLabel="Drafting…">
            Draft again
          </Button>
        </Sample>
      </Section>

      <Section title="Text fields">
        <Sample caption="Text field, empty">
          <TextField id="preview-email-empty" label="Email" type="email" />
        </Sample>
        <Sample caption="Text field, filled">
          <TextField id="preview-email-filled" label="Email" type="email" defaultValue="sam.taylor@example.com" />
        </Sample>
        <Sample caption="Text field with a hint">
          <TextField id="preview-password-hint" label="Password" type="password" hint={PASSWORD_HINT} />
        </Sample>
        <Sample caption="Text field with an error">
          <TextField
            id="preview-email-error"
            label="Email"
            type="email"
            defaultValue="sam.taylor"
            messages={['Enter an email address with an @, such as name@example.com.']}
          />
        </Sample>
        <Sample caption="Date field">
          <TextField id="preview-date" label="Date" type="date" defaultValue="2026-11-10" />
        </Sample>
        <Sample caption="Text area, empty">
          <TextArea id="preview-entry-empty" label="Entry" />
        </Sample>
        <Sample caption="Text area, filled">
          <TextArea
            id="preview-entry-filled"
            label="Entry"
            defaultValue="Shipped the new onboarding checklist two days early. Setup questions in the support channel dropped in the first week."
          />
        </Sample>
        <Sample caption="Text area with a hint">
          <TextArea id="preview-result-hint" label="Result" hint="Optional. What changed because of it?" />
        </Sample>
        <Sample caption="Text area with an error">
          <TextArea id="preview-entry-error" label="Entry" messages={['Write what happened, then save.']} />
        </Sample>
      </Section>

      <Section title="Category chips">
        <ChipSample caption="Unselected" initial={[]} />
        <ChipSample caption="Selected" initial={[...CATEGORIES]} />
        <ChipSample caption="Filter, two selected" initial={['Achievement', 'Feedback']} filter />
      </Section>

      <Section title="Category labels">
        <Sample caption="Category labels" row>
          {CATEGORIES.map((category) => (
            <CategoryLabel key={category} category={category} />
          ))}
        </Sample>
      </Section>

      <Section title="Saved message">
        <Sample caption="Saved message">
          <SavedMessage phase={saved.phase} count={saved.count}>
            Entry saved.
          </SavedMessage>
          <div className="preview__after">
            <Button variant="secondary" onClick={showSaved}>
              Show saved message
            </Button>
          </div>
        </Sample>
      </Section>

      <Section title="Messages">
        <Sample caption="Information">
          <Message variant="info">The server is waking up. This can take up to a minute.</Message>
        </Sample>
        <Sample caption="Error">
          <Message variant="error">Wrong email or password.</Message>
        </Sample>
      </Section>

      <Section title="Entry rows">
        <div className="preview__entries">
          {SAMPLE_ENTRIES.map((entry) => (
            <EntryRow key={entry.date} entry={entry} />
          ))}
        </div>
        <Sample caption="With tags">
          <EntryRow entry={TAGGED_ENTRY} tags={['onboarding', 'Leadership', 'Q4']} />
        </Sample>
        <Sample caption="With long tag names">
          <EntryRow entry={LONG_TAGS_ENTRY} tags={LONG_TAGS} />
        </Sample>
        <Sample caption="With Edit and Delete">
          <EntryRow entry={ACTIONS_ENTRY} tags={['incident']} actions={{ editTo: '#', onDelete: () => {} }} />
        </Sample>
      </Section>

      <Section title="Empty state">
        <Sample caption="Without an illustration">
          <EmptyState action={<Button variant="secondary">New entry</Button>}>{EMPTY_STATE_TEXT}</EmptyState>
        </Sample>
        <Sample caption="With an illustration">
          <EmptyState action={<Button variant="secondary">New entry</Button>} illustration={<EntriesIllustration />}>
            {EMPTY_STATE_TEXT}
          </EmptyState>
        </Sample>
        <Sample caption="The three illustrations: login and registration, empty entries list, review" row>
          <LoginIllustration />
          <EntriesIllustration />
          <ReviewIllustration />
        </Sample>
      </Section>
    </main>
  )
}
