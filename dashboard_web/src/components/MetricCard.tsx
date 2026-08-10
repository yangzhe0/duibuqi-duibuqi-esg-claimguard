type Props = {
  eyebrow: string
  value: string
  detail: string
  accent?: 'blue' | 'green' | 'gold' | 'red'
}

export function MetricCard({ eyebrow, value, detail, accent = 'blue' }: Props) {
  return (
    <article className={`metric-card accent-${accent}`}>
      <span className="metric-eyebrow">{eyebrow}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}
