import './ProvenanceBadge.css'

// Auto-assigned colors for directives
const PALETTE = [
  'var(--primary)',
  'var(--status-online)',
  'var(--status-degraded)',
  '#3b82f6',
  '#8b5cf6',
  '#14b8a6',
  '#f97316',
  '#ef4444',
]

/**
 * Small inline badge showing which directive created a work unit.
 * Color auto-assigned from directive index.
 */
export default function ProvenanceBadge({ directiveId, directiveTitle, directiveIndex = 0 }) {
  if (!directiveId) return null
  const color = PALETTE[directiveIndex % PALETTE.length]
  const label = directiveTitle || `Directive ${directiveIndex + 1}`

  return (
    <span className="prov-badge" style={{ borderColor: color }} title={`From: ${label} (${directiveId})`}>
      <span className="prov-dot" style={{ background: color }} />
      <span className="prov-label">{label.length > 20 ? label.slice(0, 18) + '...' : label}</span>
    </span>
  )
}
