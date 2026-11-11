import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SavedMessage from './SavedMessage.tsx'
import { SAVED_MESSAGE_FADE_MS, SAVED_MESSAGE_MS, useSavedMessage } from './useSavedMessage.ts'

function Harness() {
  const saved = useSavedMessage()
  return (
    <>
      <SavedMessage phase={saved.phase} count={saved.count}>
        Entry saved.
      </SavedMessage>
      <button type="button" onClick={saved.show}>
        Save
      </button>
    </>
  )
}

function save() {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('SavedMessage', () => {
  it('keeps an empty status region in the page until it is shown', () => {
    render(<Harness />)

    expect(screen.getByRole('status').textContent).toBe('')
  })

  it('is announced in the status region without moving focus', () => {
    render(<Harness />)
    const button = screen.getByRole('button', { name: 'Save' })
    button.focus()

    save()

    const status = screen.getByRole('status')
    expect(status.textContent).toBe('Entry saved.')
    expect(status.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(button)
  })

  it('is gone 5 seconds after it was shown', () => {
    render(<Harness />)
    save()

    advance(SAVED_MESSAGE_MS - SAVED_MESSAGE_FADE_MS)
    // Fading out during its last 300ms.
    expect(screen.getByRole('status').textContent).toBe('Entry saved.')
    expect(screen.getByRole('status').classList.contains('saved-region--leaving')).toBe(true)

    advance(SAVED_MESSAGE_FADE_MS - 1)
    expect(screen.getByRole('status').textContent).toBe('Entry saved.')
    advance(1)
    expect(screen.getByRole('status').textContent).toBe('')
  })

  it('starts its time again when shown while visible, and is never shown twice', () => {
    render(<Harness />)
    save()
    advance(4_000)
    const band = screen.getByRole('status').querySelector('.saved-message')

    save()

    // The same band, so it does not enter again; a single message.
    expect(screen.getByRole('status').querySelector('.saved-message')).toBe(band)
    expect(screen.getAllByText('Entry saved.')).toHaveLength(1)
    advance(4_000)
    expect(screen.getByRole('status').textContent).toBe('Entry saved.')
    advance(SAVED_MESSAGE_MS - 4_000)
    expect(screen.getByRole('status').textContent).toBe('')
  })

  it('stops fading out when shown again during its last 300ms', () => {
    render(<Harness />)
    save()
    advance(SAVED_MESSAGE_MS - 100)
    expect(screen.getByRole('status').classList.contains('saved-region--leaving')).toBe(true)

    save()

    expect(screen.getByRole('status').classList.contains('saved-region--leaving')).toBe(false)
    expect(screen.getByRole('status').textContent).toBe('Entry saved.')
  })

  it('replaces its text when shown again, so screen readers announce it again', () => {
    render(<Harness />)
    save()
    const text = screen.getByText('Entry saved.')

    save()

    expect(screen.getByText('Entry saved.')).not.toBe(text)
  })
})
