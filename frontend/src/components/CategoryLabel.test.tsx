import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CATEGORIES } from './categories.ts'
import CategoryLabel from './CategoryLabel.tsx'

describe('CategoryLabel', () => {
  it.each(CATEGORIES)('shows %s in its tint, as text that is not interactive', (category) => {
    render(<CategoryLabel category={category} />)

    const label = screen.getByText(category)
    expect(label.tagName).toBe('SPAN')
    expect(label.className).toContain(`category--${category.toLowerCase().replace(' ', '-')}`)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
