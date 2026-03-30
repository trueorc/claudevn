import './ConfidencePanel.css'

/**
 * Tiny traffic light dot for use in sidebar directive cards.
 * Shows confidence level as an 8px colored dot with tooltip.
 */
export default function ConfidenceMiniIndicator({ score, level }) {
  if (score == null) return null

  const colorClass = level === 'green' ? 'cmi--green' : level === 'yellow' ? 'cmi--yellow' : 'cmi--red'

  return (
    <span className={`cmi ${colorClass}`} title={`Confidence: ${score}/100`} />
  )
}
