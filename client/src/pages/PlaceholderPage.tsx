import type { ReactNode } from 'react'

type PlaceholderPageProps = {
  title: string
  description: string
  icon: ReactNode
}

export function PlaceholderPage({ title, description, icon }: PlaceholderPageProps) {
  return (
    <section className="placeholder-page">
      <div className="page-intro glass-panel">
        {icon}
        <div>
          <p>Coming next</p>
          <h1>{title}</h1>
          <span>{description}</span>
        </div>
      </div>
    </section>
  )
}
