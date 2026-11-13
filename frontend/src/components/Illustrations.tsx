import type { ReactNode } from 'react'
import './Illustrations.css'

// The three illustrations from DESIGN.md ("Colour blocks and illustrations", #77): one
// lilac diary with the same pencil, peach backdrop and plum line work in each. Every
// colour comes from a token through a class in Illustrations.css, so the drawings follow
// light and dark mode. They are decorative: hidden from screen readers, never focusable.
// Shapes and coordinates follow the design note on #77 (viewBox 0 0 200 160).

type Size = 'login' | 'entries' | 'review'

function Illustration({ size, children }: { size: Size; children: ReactNode }) {
  return (
    <svg
      className={`illustration illustration--${size}`}
      viewBox="0 0 200 160"
      aria-hidden="true"
      focusable="false"
    >
      {/* Shared by all three: the backdrop circle and the ground line. */}
      <circle className="illustration__backdrop" cx="100" cy="82" r="64" />
      <line className="illustration__line" x1="8" y1="148" x2="192" y2="148" />
      {children}
    </svg>
  )
}

/** The shared pencil, tip at 0,0 pointing up, 72 long; placed with a transform. */
function Pencil({ transform }: { transform: string }) {
  return (
    <g transform={transform}>
      <polygon className="illustration__shape illustration__shape--apricot" points="0,0 7,14 -7,14" />
      <polygon className="illustration__accent" points="0,0 2.5,5 -2.5,5" />
      <rect className="illustration__shape illustration__shape--sage" x="-7" y="14" width="14" height="48" />
      <rect className="illustration__shape illustration__shape--rose" x="-7" y="62" width="14" height="10" rx="2" />
    </g>
  )
}

/** Login and registration: a closed diary with a star, a pencil beside it, a little applause. */
export function LoginIllustration() {
  return (
    <Illustration size="login">
      <rect className="illustration__dot--feedback" x="104" y="38" width="10" height="18" />
      <rect className="illustration__shape illustration__shape--lilac" x="64" y="50" width="64" height="98" rx="8" />
      <line className="illustration__line" x1="78" y1="52" x2="78" y2="146" />
      <polygon
        className="illustration__accent"
        points="103,84 105,89.2 110.6,89.5 106.2,93.1 107.7,98.5 103,95.4 98.3,98.5 99.8,93.1 95.4,89.5 101,89.2"
      />
      <Pencil transform="translate(133 78) rotate(-16)" />
      <line className="illustration__line" x1="52" y1="42" x2="44" y2="35" />
      <line className="illustration__line" x1="58" y1="38" x2="57" y2="28" />
      <line className="illustration__line" x1="48" y1="49" x2="38" y2="50" />
      <circle className="illustration__dot--achievement" cx="150" cy="34" r="5" />
      <circle className="illustration__dot--side-project" cx="166" cy="54" r="5" />
    </Illustration>
  )
}

/** Empty entries list: the same diary open at two blank pages, the pencil ready. */
export function EntriesIllustration() {
  return (
    <Illustration size="entries">
      <path
        className="illustration__shape illustration__shape--lilac"
        d="M32 66 L32 142 Q68 136 100 146 Q132 136 168 142 L168 66 Z"
      />
      <path className="illustration__shape illustration__shape--apricot" d="M100 62 Q72 50 40 58 L40 132 Q72 126 100 138 Z" />
      <path
        className="illustration__shape illustration__shape--apricot"
        d="M100 62 Q128 50 160 58 L160 132 Q128 126 100 138 Z"
      />
      <Pencil transform="translate(118 112) rotate(-136)" />
      <line className="illustration__line" x1="44" y1="40" x2="37" y2="33" />
      <line className="illustration__line" x1="51" y1="36" x2="50" y2="26" />
      <line className="illustration__line" x1="40" y1="47" x2="30" y2="47" />
      <circle className="illustration__dot--learning" cx="70" cy="30" r="5" />
      <circle className="illustration__dot--feedback" cx="150" cy="30" r="5" />
    </Illustration>
  )
}

/** Review with no matching entries: a written page, a magnifier over its empty part. */
export function ReviewIllustration() {
  return (
    <Illustration size="review">
      <rect className="illustration__shape illustration__shape--apricot" x="50" y="36" width="76" height="112" rx="8" />
      <line className="illustration__line" x1="64" y1="58" x2="110" y2="58" />
      <line className="illustration__line" x1="64" y1="72" x2="102" y2="72" />
      <line className="illustration__line" x1="64" y1="86" x2="94" y2="86" />
      <rect
        className="illustration__handle"
        x="-7"
        y="0"
        width="14"
        height="34"
        rx="7"
        transform="translate(146 120) rotate(-45)"
      />
      <circle className="illustration__shape illustration__shape--lilac" cx="126" cy="100" r="28" />
      <path className="illustration__line" d="M109 94 A18 18 0 0 1 120 83" />
      <circle className="illustration__dot--achievement" cx="146" cy="30" r="5" />
      <circle className="illustration__dot--side-project" cx="162" cy="46" r="5" />
    </Illustration>
  )
}
