import { fireEvent, render, screen, within } from '@testing-library/react'
import { createRef, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EntryRow from './EntryRow.tsx'
import { formatFullDate, formatMonthHeading, formatShortDate } from './formatDate.ts'

const ENTRY = {
  date: '2026-11-10',
  category: 'Achievement' as const,
  text: 'Shipped the new onboarding checklist two days early.',
  result_impact: 'Setup tickets went from 14 to 5 a week.',
}

describe('EntryRow', () => {
  it('shows the date, category label, text and result', () => {
    render(<EntryRow entry={ENTRY} />)

    const date = screen.getByText('10 Nov')
    expect(date.tagName).toBe('TIME')
    expect(date.getAttribute('datetime')).toBe('2026-11-10')
    expect(screen.getByText('Achievement').classList.contains('category-label')).toBe(true)
    expect(screen.getByText(ENTRY.text)).toBeTruthy()
    const result = screen.getByText('Result:').parentElement as HTMLElement
    expect(result.textContent).toBe('Result: Setup tickets went from 14 to 5 a week.')
  })

  it.each([null, ''])('has no result line when the result is %j', (result) => {
    render(<EntryRow entry={{ ...ENTRY, result_impact: result }} />)

    expect(screen.queryByText(/Result/)).toBeNull()
  })

  it('keeps line breaks in the text', () => {
    const text = 'Led the incident review.\nWrote the timeline.'
    render(<EntryRow entry={{ ...ENTRY, text }} />)

    const paragraph = document.querySelector('.entry-row__text') as HTMLElement
    expect(paragraph.textContent).toBe(text)
  })
})

function inRouter(children: ReactNode) {
  return <MemoryRouter>{children}</MemoryRouter>
}

describe('EntryRow without tags and actions ("Just saved", #27)', () => {
  it('has no tag area, no actions and no actions layout', () => {
    render(<EntryRow entry={ENTRY} />)

    expect(screen.queryByRole('list')).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.queryByRole('button')).toBeNull()
    expect(document.querySelector('.entry-row__category')?.className).toBe('entry-row__category')
  })
})

describe('EntryRow with tags and actions (#29)', () => {
  it('shows the tags read-only, with their stored spelling, below the text and result', () => {
    render(<EntryRow entry={ENTRY} tags={['incident', 'Leadership', 'a-very-long-tag-name-without-spaces']} />)

    const list = screen.getByRole('list', { name: 'Tags' })
    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'incident',
      'Leadership',
      'a-very-long-tag-name-without-spaces',
    ])
    expect(within(list).queryByRole('button')).toBeNull()
    const body = document.querySelector('.entry-row__body') as HTMLElement
    expect(body.lastElementChild).toBe(list)
  })

  it('has no tag area for an empty tag list', () => {
    render(<EntryRow entry={ENTRY} tags={[]} />)

    expect(screen.queryByRole('list')).toBeNull()
  })

  it('has Edit as a link and Delete as a button, named with the full date', () => {
    const onDelete = vi.fn()
    const editRef = createRef<HTMLAnchorElement>()
    const deleteRef = createRef<HTMLButtonElement>()
    render(
      inRouter(
        <EntryRow
          entry={ENTRY}
          actions={{ editTo: '/entries/42/edit', onDelete }}
          editRef={editRef}
          deleteRef={deleteRef}
        />,
      ),
    )

    const edit = screen.getByRole('link', { name: 'Edit entry from 10 Nov 2026' })
    expect(edit.getAttribute('href')).toBe('/entries/42/edit')
    expect(edit.textContent).toBe('')
    expect(editRef.current).toBe(edit)
    const remove = screen.getByRole('button', { name: 'Delete entry from 10 Nov 2026' })
    expect(remove.getAttribute('type')).toBe('button')
    expect(deleteRef.current).toBe(remove)
    // Next to the category label, in the same column.
    expect(remove.closest('.entry-row__category')?.classList.contains('entry-row__category--with-actions')).toBe(true)
    fireEvent.click(remove)
    expect(onDelete).toHaveBeenCalledTimes(1)
  })
})

describe('the entry date has no time-zone shift', () => {
  beforeEach(() => {
    // Behind UTC: there, new Date('2026-11-10') is still 9 November.
    vi.stubEnv('TZ', 'America/Los_Angeles')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows the stored day in a time zone behind UTC', () => {
    expect(new Date('2026-11-10').getDate()).toBe(9)

    render(<EntryRow entry={ENTRY} />)

    expect(screen.getByText('10 Nov')).toBeTruthy()
    expect(screen.queryByText('9 Nov')).toBeNull()
  })

  it.each([
    ['2026-11-10', '10 Nov'],
    ['2026-11-01', '1 Nov'],
    ['2026-09-30', '30 Sep'],
    ['2026-01-01', '1 Jan'],
    ['2026-12-31', '31 Dec'],
  ])('formats %s as "%s"', (stored, shown) => {
    expect(formatShortDate(stored)).toBe(shown)
  })

  it.each([
    ['2026-11-10', '10 Nov 2026', 'November 2026'],
    ['2026-11-01', '1 Nov 2026', 'November 2026'],
    ['2026-12-31', '31 Dec 2026', 'December 2026'],
    ['2027-01-05', '5 Jan 2027', 'January 2027'],
    ['2026-09-30', '30 Sep 2026', 'September 2026'],
  ])('formats %s as "%s" under "%s"', (stored, full, month) => {
    expect(formatFullDate(stored)).toBe(full)
    expect(formatMonthHeading(stored)).toBe(month)
  })
})
