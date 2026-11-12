import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { addStylesheet } from '../test/entryForm.ts'
import { TextArea, TextField } from './TextField.tsx'

const HINT = 'At least 10 characters, including an uppercase letter, a number and a special character.'

describe('TextField', () => {
  it('has a visible label above the input', () => {
    render(<TextField id="email" label="Email" type="email" />)

    const input = screen.getByLabelText('Email') as HTMLInputElement
    expect(input.type).toBe('email')
    const label = screen.getByText('Email')
    expect(label.tagName).toBe('LABEL')
    expect(label.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(input.getAttribute('aria-invalid')).toBe('false')
    expect(input.getAttribute('aria-describedby')).toBeNull()
  })

  it.each(['text', 'email', 'password', 'date'])('works for %s input', (type) => {
    render(<TextField id="field" label="Field" type={type} defaultValue={type === 'date' ? '2026-11-10' : 'value'} />)

    const input = screen.getByLabelText('Field') as HTMLInputElement
    expect(input.type).toBe(type)
    expect(input.value).toBe(type === 'date' ? '2026-11-10' : 'value')
  })

  it('links the hint to the input', () => {
    render(<TextField id="password" label="Password" type="password" hint={HINT} />)

    const hint = screen.getByText(HINT)
    expect(hint.id).toBe('password-hint')
    expect(screen.getByLabelText('Password').getAttribute('aria-describedby')).toBe('password-hint')
  })

  it('shows the error state: messages below, linked, announced and aria-invalid', () => {
    render(
      <TextField
        id="email"
        label="Email"
        type="email"
        hint="Your work email."
        defaultValue="sam.taylor"
        messages={['Enter an email address with an @, such as name@example.com.']}
      />,
    )

    const input = screen.getByLabelText('Email')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    const messages = document.getElementById('email-messages') as HTMLElement
    expect(messages.getAttribute('role')).toBe('alert')
    expect(messages.textContent).toBe('Enter an email address with an @, such as name@example.com.')
    expect(input.getAttribute('aria-describedby')).toBe('email-hint email-messages')
    expect(input.compareDocumentPosition(messages) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('keeps the empty message region in the page, so new messages are announced', () => {
    render(<TextField id="email" label="Email" />)

    expect(document.getElementById('email-messages')?.getAttribute('role')).toBe('alert')
  })

  it('shows content after the input, such as a Show button', () => {
    render(<TextField id="password" label="Password" type="password" after={<button type="button">Show</button>} />)

    expect(screen.getByRole('button', { name: 'Show' })).toBeTruthy()
  })
})

describe('date input', () => {
  it('uses tabular figures (DESIGN.md → Typography); other inputs do not', async () => {
    const remove = await addStylesheet('components/TextField.css')
    try {
      render(
        <>
          <TextField id="date" label="Date" type="date" defaultValue="2026-11-02" />
          <TextField id="name" label="Name" />
        </>,
      )

      expect(getComputedStyle(screen.getByLabelText('Date')).fontVariantNumeric).toBe('tabular-nums')
      expect(getComputedStyle(screen.getByLabelText('Name')).fontVariantNumeric).not.toBe('tabular-nums')
    } finally {
      remove()
    }
  })
})

describe('TextArea', () => {
  it('has a label, a hint and messages linked like the text field', () => {
    render(<TextArea id="entry" label="Entry" hint="Optional. What changed because of it?" messages={['Write what happened, then save.']} />)

    const area = screen.getByLabelText('Entry')
    expect(area.tagName).toBe('TEXTAREA')
    expect(area.getAttribute('aria-invalid')).toBe('true')
    expect(area.getAttribute('aria-describedby')).toBe('entry-hint entry-messages')
    expect(screen.getByRole('alert').textContent).toBe('Write what happened, then save.')
  })

  it('is valid without messages', () => {
    render(<TextArea id="entry" label="Entry" defaultValue="Shipped the checklist." />)

    const area = screen.getByLabelText('Entry') as HTMLTextAreaElement
    expect(area.value).toBe('Shipped the checklist.')
    expect(area.getAttribute('aria-invalid')).toBe('false')
  })
})
