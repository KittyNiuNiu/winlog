type PlaceholderPageProps = {
  title: string
}

// Stand-in for a page whose real content comes in a later task.
export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <section className="page">
      <h1>{title}</h1>
      <p>This page is coming soon.</p>
    </section>
  )
}
