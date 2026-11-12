import type { Category } from '../api/index.ts'
import { categoryClassName } from './categories.ts'
import './categories.css'
import './CategoryLabel.css'

interface CategoryLabelProps {
  category: Category
}

/** A small label in the category's tint, shown on every entry. Not interactive. */
export default function CategoryLabel({ category }: CategoryLabelProps) {
  return <span className={`category-label ${categoryClassName(category)}`}>{category}</span>
}
