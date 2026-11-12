import { fireEvent, render, screen } from '@testing-library/react'
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
    expect(button.disabled).toBe(true)
    const spinner = button.querySelector('.spinner')
    expect(spinner?.getAttribute('aria-hidden')).toBe('true')
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
