import type { Category } from '../api/index.ts'

/** The four categories, in the order the app shows them (openapi.yaml Category). */
export const CATEGORIES: readonly Category[] = ['Achievement', 'Learning', 'Feedback', 'Side project']

/** The CSS class that sets a category's tint, text and dot colours (categories.css). */
export function categoryClassName(category: Category): string {
  return `category--${category.toLowerCase().replace(/\s+/g, '-')}`
}
