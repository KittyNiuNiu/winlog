import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { Category } from '../api/index.ts'
import { CATEGORIES } from './categories.ts'
import CategoryChip from './CategoryChip.tsx'

function ToggleChip({ category, filter = false }: { category: Category; filter?: boolean }) {
  const [selected, setSelected] = useState(false)
  return (
    <CategoryChip
      category={category}
      selected={selected}
      onToggle={() => setSelected((current) => !current)}
      filter={filter}
    />
  )
}

describe('CategoryChip', () => {
  it.each(CATEGORIES)('shows %s with its dot and announces whether it is selected', (category) => {
    const { rerender } = render(<CategoryChip category={category} selected={false} onToggle={() => {}} />)

    const chip = screen.getByRole('button', { name: category })
    expect(chip.getAttribute('aria-pressed')).toBe('false')
    expect(chip.querySelector('.chip__dot')?.getAttribute('aria-hidden')).toBe('true')
    expect(chip.className).toContain(`category--${category.toLowerCase().replace(' ', '-')}`)

    rerender(<CategoryChip category={category} selected onToggle={() => {}} />)
    expect(screen.getByRole('button', { name: category, pressed: true })).toBeTruthy()
  })

  it('is selected and unselected with Space and Enter', async () => {
    const user = userEvent.setup()
    render(<ToggleChip category="Learning" />)
    const chip = screen.getByRole('button', { name: 'Learning' })

    await user.tab()
    expect(document.activeElement).toBe(chip)
    await user.keyboard(' ')
    expect(chip.getAttribute('aria-pressed')).toBe('true')
    await user.keyboard('{Enter}')
    expect(chip.getAttribute('aria-pressed')).toBe('false')
  })

  it('is selected and unselected with a click or tap', async () => {
    const user = userEvent.setup()
    render(<ToggleChip category="Feedback" />)
    const chip = screen.getByRole('button', { name: 'Feedback' })

    await user.click(chip)
    expect(chip.getAttribute('aria-pressed')).toBe('true')
    await user.click(chip)
    expect(chip.getAttribute('aria-pressed')).toBe('false')
  })

  it('has no check icon outside filters', () => {
    render(<CategoryChip category="Achievement" selected onToggle={() => {}} />)

    expect(screen.getByRole('button', { name: 'Achievement' }).querySelector('svg')).toBeNull()
  })

  it('filter variant: a selected chip has a check icon, hidden from screen readers', async () => {
    const user = userEvent.setup()
    render(<ToggleChip category="Side project" filter />)
    const chip = screen.getByRole('button', { name: 'Side project' })
    expect(chip.querySelector('svg')).toBeNull()

    await user.click(chip)

    const check = chip.querySelector('svg')
    expect(check?.getAttribute('aria-hidden')).toBe('true')
    expect(check?.getAttribute('width')).toBe('16')
    // The icon adds nothing to the name.
    expect(screen.getByRole('button', { name: 'Side project', pressed: true })).toBe(chip)
  })
})
