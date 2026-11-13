import { fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { describe, expect, it } from 'vitest'
import ComponentPreviewPage from './ComponentPreviewPage.tsx'

function renderPreview() {
  const router = createMemoryRouter([{ path: '/', element: <ComponentPreviewPage /> }])
  return render(<RouterProvider router={router} />)
}

const SECTIONS = [
  'Wordmark',
  'Buttons',
  'Text fields',
  'Category chips',
  'Category labels',
  'Saved message',
  'Messages',
  'Entry rows',
  'Empty state',
]

describe('component preview (development only)', () => {
  it('has a section for every shared component, in order', () => {
    renderPreview()

    expect(screen.getByRole('heading', { level: 1, name: 'Component preview' })).toBeTruthy()
    expect(screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)).toEqual(SECTIONS)
  })

  it('shows the buttons in their normal, disabled and busy states', () => {
    renderPreview()

    const buttons = screen.getAllByRole('button').map((button) => [
      button.textContent,
      (button as HTMLButtonElement).disabled,
      button.getAttribute('aria-busy'),
      button.getAttribute('aria-disabled'),
    ])
    // Busy buttons are announced as unavailable but not natively disabled, so they keep focus (#84).
    expect(buttons).toEqual(
      expect.arrayContaining([
        ['Log in', false, 'false', null],
        ['Log in', true, 'false', null],
        ['Logging in…', false, 'true', 'true'],
        ['Save entry', false, 'false', null],
        ['Draft again', false, 'false', null],
        ['Draft again', true, 'false', null],
        ['Drafting…', false, 'true', 'true'],
      ]),
    )
  })

  it('shows the text fields and text areas: empty, filled, with a hint and with an error', () => {
    renderPreview()

    expect(screen.getAllByLabelText('Email')).toHaveLength(3)
    expect(screen.getByDisplayValue('sam.taylor@example.com')).toBeTruthy()
    expect(screen.getByLabelText('Date')).toHaveProperty('value', '2026-11-10')
    expect(screen.getAllByLabelText('Entry')).toHaveLength(3)
    const invalid = document.querySelectorAll('[aria-invalid="true"]')
    expect(invalid).toHaveLength(2)
    expect(screen.getByText('Optional. What changed because of it?')).toBeTruthy()
  })

  it('shows all four chips unselected, selected and as filters', () => {
    renderPreview()

    for (const category of ['Achievement', 'Learning', 'Feedback', 'Side project']) {
      expect(screen.getAllByRole('button', { name: category, pressed: false }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('button', { name: category, pressed: true }).length).toBeGreaterThan(0)
    }
    const filters = screen.getByText('Filter, two selected').closest('figure') as HTMLElement
    expect(within(filters).getAllByRole('button', { pressed: true }).map((chip) => chip.textContent)).toEqual([
      'Achievement',
      'Feedback',
    ])
    fireEvent.click(within(filters).getByRole('button', { name: 'Learning' }))
    expect(within(filters).getByRole('button', { name: 'Learning' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('shows the saved message when it opens, and again with "Show saved message"', () => {
    renderPreview()

    const status = screen.getByText('Entry saved.').closest('[role="status"]') as HTMLElement
    expect(status.textContent).toBe('Entry saved.')
    fireEvent.click(screen.getByRole('button', { name: 'Show saved message' }))
    expect(within(status).getAllByText('Entry saved.')).toHaveLength(1)
  })

  it('shows both message variants', () => {
    renderPreview()

    expect(screen.getByText('The server is waking up. This can take up to a minute.').getAttribute('role')).toBe('status')
    expect(screen.getByText('Wrong email or password.').getAttribute('role')).toBe('alert')
  })

  it('shows entry rows with and without a result, in German and in Japanese', () => {
    renderPreview()

    expect(screen.getAllByText('Result:')).toHaveLength(3)
    expect(screen.getByText(/^Gelernt, wie wir Datenbankmigrationen/)).toBeTruthy()
    expect(screen.getByText('週末に家計簿アプリの試作版を作り、友人3人に使ってもらった。')).toBeTruthy()
    expect(screen.getByText('30 Sep').getAttribute('datetime')).toBe('2026-09-30')
    expect(document.body.textContent).not.toMatch(/lorem|ipsum/i)
  })

  it('shows entry rows with tags, with long tag names, and with Edit and Delete (#29)', () => {
    renderPreview()

    const tagged = screen.getByText('With tags').closest('figure') as HTMLElement
    expect(within(tagged).getByRole('list', { name: 'Tags' })).toBeTruthy()
    const long = screen.getByText('With long tag names').closest('figure') as HTMLElement
    expect(within(long).getByText('database-transaction-isolation-levels-and-locking')).toBeTruthy()
    const actions = screen.getByText('With Edit and Delete').closest('figure') as HTMLElement
    expect(within(actions).getByRole('link', { name: 'Edit entry from 4 Nov 2026' })).toBeTruthy()
    expect(within(actions).getByRole('button', { name: 'Delete entry from 4 Nov 2026' })).toBeTruthy()
  })

  it('shows the empty state with and without an illustration placeholder', () => {
    renderPreview()

    const text = 'No entries yet. One sentence about something that went well is enough to start.'
    expect(screen.getAllByText(text)).toHaveLength(2)
    expect(document.querySelectorAll('.empty-state__illustration')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'New entry' })).toHaveLength(2)
  })
})
