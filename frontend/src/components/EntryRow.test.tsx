import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EntryRow from './EntryRow.tsx'
import { formatShortDate } from './formatDate.ts'

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
})
