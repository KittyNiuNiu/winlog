import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EmptyState from './EmptyState.tsx'

const TEXT = 'No entries yet. One sentence about something that went well is enough to start.'

describe('EmptyState', () => {
  it('shows the sentence and one action without an illustration', () => {
    const { container } = render(<EmptyState action={<button type="button">New entry</button>}>{TEXT}</EmptyState>)

    expect(screen.getByText(TEXT)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'New entry' })).toBeTruthy()
    expect(container.querySelector('.empty-state__illustration')).toBeNull()
  })

  it('shows a decorative illustration above the sentence, hidden from screen readers', () => {
    const { container } = render(
      <EmptyState action={<button type="button">New entry</button>} illustration={<div data-testid="art" />}>
        {TEXT}
      </EmptyState>,
    )

    const slot = container.querySelector('.empty-state__illustration') as HTMLElement
    expect(slot.getAttribute('aria-hidden')).toBe('true')
    expect(slot.contains(screen.getByTestId('art'))).toBe(true)
    expect(slot.compareDocumentPosition(screen.getByText(TEXT)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
