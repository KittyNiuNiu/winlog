import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Message from './Message.tsx'

describe('Message', () => {
  it('information: a status region with the information icon and the text', () => {
    render(<Message variant="info">The server is waking up. This can take up to a minute.</Message>)

    const message = screen.getByRole('status')
    expect(message.textContent).toBe('The server is waking up. This can take up to a minute.')
    expect(message.classList.contains('message--info')).toBe(true)
    const icon = message.querySelector('svg')
    expect(icon?.getAttribute('aria-hidden')).toBe('true')
    expect(icon?.classList.contains('lucide-info')).toBe(true)
  })

  it('error: an alert region with the error icon and the text', () => {
    render(<Message variant="error">Wrong email or password.</Message>)

    const message = screen.getByRole('alert')
    expect(message.textContent).toBe('Wrong email or password.')
    expect(message.classList.contains('message--error')).toBe(true)
    const icon = message.querySelector('svg')
    expect(icon?.getAttribute('aria-hidden')).toBe('true')
    expect(icon?.getAttribute('class')).toMatch(/lucide-circle-(alert|exclamation-point)/)
  })

  it('not live: no role, so it is not announced again (the demo notice, #35)', () => {
    const { container } = render(
      <Message variant="info" live={false}>
        Shown on every page.
      </Message>,
    )

    const message = container.firstElementChild as HTMLElement
    expect(message.getAttribute('role')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    expect(message.textContent).toBe('Shown on every page.')
    expect(message.classList.contains('message--info')).toBe(true)
    expect(message.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })

  it.each([null, ''])('without text (%j), keeps an empty live region in the page', (text) => {
    render(<Message variant="error">{text}</Message>)

    const message = screen.getByRole('alert')
    expect(message.childNodes).toHaveLength(0)
  })
})
