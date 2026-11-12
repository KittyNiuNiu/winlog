import type { LucideIcon } from 'lucide-react'

interface IconProps {
  /** The lucide-react icon to draw. */
  icon: LucideIcon
  /** Width and height in px: 16, 20 or 24. */
  size: 16 | 20 | 24
  className?: string
}

// Every icon in the app (DESIGN.md → Icons): an outline icon from lucide-react in the
// current text colour, drawn with a 1.75px stroke at every size. Each icon sits next to a
// visible text label, so it is hidden from screen readers.
export default function Icon({ icon: LucideComponent, size, className }: IconProps) {
  return (
    <LucideComponent
      className={className}
      size={size}
      strokeWidth={1.75}
      absoluteStrokeWidth
      aria-hidden="true"
      focusable="false"
    />
  )
}
