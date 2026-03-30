import { ChevronRight } from 'lucide-react'
import './ComplexityProfile.css'

const COMPLEXITY_COLORS = {
  xs: 'var(--status-online)',
  s: 'var(--status-online)',
  m: 'var(--text-secondary)',
  l: 'var(--status-degraded)',
  xl: 'var(--status-offline)',
}

/**
 * Per-directive complexity breakdown — horizontal bars showing
 * work unit count, complexity distribution, and confidence.
 * Each row is clickable to navigate to the directive.
 */
export default function ComplexityProfile({ goals, allWorkUnits, allScores, onSelectGoal }) {
  const rows = goals
    .map(g => {
      const units = allWorkUnits.get(g.goal_id) || []
      if (units.length === 0) return null

      const scores = allScores.get(g.goal_id)
      const complexityCounts = { xs: 0, s: 0, m: 0, l: 0, xl: 0 }
      for (const u of units) {
        const c = (u.estimated_complexity || 'm').toLowerCase()
        complexityCounts[c] = (complexityCounts[c] || 0) + 1
      }

      return {
        goal: g,
        units,
        complexityCounts,
        confidence: scores?.score ?? null,
        confidenceLevel: scores?.level ?? null,
      }
    })
    .filter(Boolean)

  if (rows.length === 0) return null

  const maxUnits = Math.max(...rows.map(r => r.units.length))

  return (
    <div className="cxp">
      <div className="cxp-header">
        <span className="cxp-title">Complexity by Directive</span>
      </div>
      <div className="cxp-rows">
        {rows.map(row => (
          <button
            key={row.goal.goal_id}
            className="cxp-row"
            onClick={() => onSelectGoal?.(row.goal)}
          >
            <span className="cxp-row-label">
              {row.goal.title || row.goal.description?.slice(0, 40) || row.goal.goal_id}
            </span>

            <div className="cxp-bar-container">
              <div className="cxp-bar" style={{ width: `${(row.units.length / maxUnits) * 100}%` }}>
                {Object.entries(row.complexityCounts).map(([level, count]) => {
                  if (count === 0) return null
                  const pct = (count / row.units.length) * 100
                  return (
                    <div
                      key={level}
                      className="cxp-bar-segment"
                      style={{ width: `${pct}%`, background: COMPLEXITY_COLORS[level] }}
                      title={`${count} ${level.toUpperCase()}`}
                    />
                  )
                })}
              </div>
            </div>

            <span className="cxp-row-count">{row.units.length} units</span>

            {row.confidence != null && (
              <span className={`cxp-row-confidence cxp-confidence--${row.confidenceLevel}`}>
                {row.confidence}
              </span>
            )}

            <ChevronRight size={12} className="cxp-row-arrow" />
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="cxp-legend">
        {['xs', 's', 'm', 'l', 'xl'].map(level => (
          <span key={level} className="cxp-legend-item">
            <span className="cxp-legend-dot" style={{ background: COMPLEXITY_COLORS[level] }} />
            {level.toUpperCase()}
          </span>
        ))}
      </div>
    </div>
  )
}
