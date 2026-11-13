import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { FormEvent } from 'react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { describe, expect, it, vi } from 'vitest'
import { Button, ButtonLink } from './Button.tsx'

describe('Button', () => {
  it('is a primary button by default and calls onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Log in</Button>)

    const button = screen.getByRole('button', { name: 'Log in' }) as HTMLButtonElement
    expect(button.type).toBe('button')
    expect(button.classList.contains('button--primary')).toBe(true)
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('has a secondary variant and a large size', () => {
    render(
      <>
        <Button variant="secondary">Draft again</Button>
        <Button size="large">Save entry</Button>
      </>,
    )

    expect(screen.getByRole('button', { name: 'Draft again' }).classList.contains('button--secondary')).toBe(true)
    expect(screen.getByRole('button', { name: 'Save entry' }).classList.contains('button--large')).toBe(true)
  })

  it('cannot be pressed when disabled', () => {
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        Log in
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Log in' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows a spinner and the busy label while busy, and cannot be pressed again', () => {
    const onClick = vi.fn()
    render(
      <Button busy busyLabel="Logging in…" onClick={onClick}>
        Log in
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Logging in…' }) as HTMLButtonElement
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.getAttribute('aria-disabled')).toBe('true')
    expect(button.disabled).toBe(false)
    const spinner = button.querySelector('.spinner')
    expect(spinner?.getAttribute('aria-hidden')).toBe('true')
    fireEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('keeps focus when it becomes busy and after it is done (#84)', () => {
    function Harness({ busy }: { busy: boolean }) {
      return (
        <Button busy={busy} busyLabel="Saving…">
          Save entry
        </Button>
      )
    }
    const { rerender } = render(<Harness busy={false} />)
    const button = screen.getByRole('button', { name: 'Save entry' })
    button.focus()
    expect(document.activeElement).toBe(button)

    rerender(<Harness busy />)
    expect(screen.getByRole('button', { name: 'Saving…' })).toBe(button)
    expect(document.activeElement).toBe(button)

    rerender(<Harness busy={false} />)
    expect(document.activeElement).toBe(button)
    expect(button.getAttribute('aria-disabled')).toBeNull()
  })

  it('ignores click, Enter and Space while busy (#84)', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <Button busy busyLabel="Saving…" onClick={onClick}>
        Save entry
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Saving…' })

    await user.click(button)
    expect(document.activeElement).toBe(button)
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(onClick).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(button)
  })

  it('does not submit its form while busy (#84)', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault())
    render(
      <form onSubmit={onSubmit}>
        <input aria-label="Email" />
        <Button type="submit" busy busyLabel="Logging in…">
          Log in
        </Button>
      </form>,
    )
    const button = screen.getByRole('button', { name: 'Logging in…' })

    await user.click(button)
    button.focus()
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('is natively disabled with disabled and without busy (#84)', () => {
    render(<Button disabled>Log in</Button>)

    const button = screen.getByRole('button', { name: 'Log in' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('aria-busy')).toBe('false')
  })

  it('applies the busy behaviour when busy and disabled are both set (#84)', () => {
    const onClick = vi.fn()
    render(
      <Button busy disabled busyLabel="Opening the demo…" onClick={onClick}>
        Try the demo
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Opening the demo…' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect(button.getAttribute('aria-disabled')).toBe('true')
    button.focus()
    expect(document.activeElement).toBe(button)
    fireEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('ButtonLink', () => {
  it('is a link styled as a secondary button', () => {
    const router = createMemoryRouter([{ path: '/', element: <ButtonLink to="/entries/new">New entry</ButtonLink> }])
    render(<RouterProvider router={router} />)

    const link = screen.getByRole('link', { name: 'New entry' })
    expect(link.getAttribute('href')).toBe('/entries/new')
    expect(link.classList.contains('button--secondary')).toBe(true)
  })
})
