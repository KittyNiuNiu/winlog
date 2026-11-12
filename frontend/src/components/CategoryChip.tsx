import { Check, Sparkles } from 'lucide-react'
import type { Category } from '../api/index.ts'
import { categoryClassName } from './categories.ts'
import Icon from './Icon.tsx'
import './categories.css'
import './CategoryChip.css'

interface CategoryChipProps {
  category: Category
  selected: boolean
  /** Called on a click, a tap, or Space or Enter. */
  onToggle: () => void
  /** The filter variant shows a check icon on a selected chip. */
  filter?: boolean
  /**
   * An AI suggestion selected this chip (#28): a dashed border and the mark "Suggested".
   * Screen readers hear "<category>, suggested".
   */
  suggested?: boolean
}

/**
 * A category chip: a toggle button with the category's dot before its label. Screen
 * readers announce whether it is selected (aria-pressed).
 */
export default function CategoryChip({
  category,
  selected,
  onToggle,
  filter = false,
  suggested = false,
}: CategoryChipProps) {
  return (
    <button
      type="button"
      className={['chip', categoryClassName(category), suggested && 'chip--suggested'].filter(Boolean).join(' ')}
      aria-pressed={selected}
      onClick={onToggle}
    >
      {filter && selected && <Icon className="chip__check" icon={Check} size={16} />}
      <span className="chip__dot" aria-hidden="true" />
      <span className="chip__label">{category}</span>
      {suggested && (
        <>
          <span className="visually-hidden">, suggested</span>
          <span className="chip__mark" aria-hidden="true">
            <Icon icon={Sparkles} size={16} />
            Suggested
          </span>
        </>
      )}
    </button>
  )
}
