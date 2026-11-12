import type { ReactNode } from 'react'

type PlaceholderPageProps = {
  title: string
  /** Shown above the title, for example the "Entry saved." message. */
  notice?: ReactNode
}

// Stand-in for a page whose real content comes in a later task.
export default function PlaceholderPage({ title, notice }: PlaceholderPageProps) {
  return (
    <section className="page">
      {notice}
      <h1>{title}</h1>
      <p>This page is coming soon.</p>
    </section>
  )
}
