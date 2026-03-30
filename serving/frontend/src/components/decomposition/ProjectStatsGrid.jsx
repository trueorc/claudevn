import { Activity, Gauge, FileCode, Layers } from 'lucide-react'
import './ProjectStatsGrid.css'

/**
 * Aggregate stats across all directives — 4-card grid.
 * Reuses the ds-grid pattern from DecompositionSummary.
 */
export default function ProjectStatsGrid({ goals, allWorkUnits, allScores }) {
  // Total work units + status breakdown
  let totalUnits = 0
  const statusCounts = {}
  for (const units of allWorkUnits.values()) {
    totalUnits += units.length
    for (const u of units) {
      statusCounts[u.status] = (statusCounts[u.status] || 0) + 1
    }
  }

  // Average confidence (weighted by unit count)
  let weightedScore = 0, totalWeight = 0
  for (const [gid, scores] of allScores.entries()) {
    if (scores?.score != null) {
      const unitCount = (allWorkUnits.get(gid) || []).length || 1
      weightedScore += scores.score * unitCount
      totalWeight += unitCount
    }
  }
  const avgConfidence = totalWeight > 0 ? Math.round(weightedScore / totalWeight) : null
  const confidenceLevel = avgConfidence >= 75 ? 'green' : avgConfidence >= 50 ? 'yellow' : avgConfidence != null ? 'red' : null

  // Total unique files
  const allFiles = new Set()
  for (const units of allWorkUnits.values()) {
    for (const u of units) {
      (u.formal_spec?.target_files || []).forEach(f => allFiles.add(f))
    }
  }

  // Complexity: total deps + directives with decompositions
  let totalDeps = 0
  for (const units of allWorkUnits.values()) {
    for (const u of units) {
      totalDeps += (u.independence?.depends_on?.length || 0)
    }
  }
  const decomposedCount = Array.from(allWorkUnits.values()).filter(u => u.length > 0).length

  return (
    <div className="psg-grid">
      {/* Work Units */}
      <div className="psg-card">
        <div className="psg-card-header">
          <Activity size={16} />
          <span className="psg-card-title">Work Units</span>
        </div>
        <div className="psg-card-body">
          <span className="psg-card-value">{totalUnits}</span>
          <div className="psg-status-pills">
            {Object.entries(statusCounts).map(([status, count]) => (
              <span key={status} className={`psg-pill psg-pill--${status}`}>
                {count} {status}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Confidence */}
      <div className={`psg-card ${confidenceLevel ? `psg-card--${confidenceLevel}` : ''}`}>
        <div className="psg-card-header">
          <Gauge size={16} />
          <span className="psg-card-title">Confidence</span>
        </div>
        <div className="psg-card-body">
          <span className={`psg-card-value ${confidenceLevel ? `psg-value--${confidenceLevel}` : ''}`}>
            {avgConfidence != null ? `${avgConfidence}/100` : '—'}
          </span>
          <span className="psg-card-detail">
            {allScores.size} directive{allScores.size !== 1 ? 's' : ''} scored
          </span>
        </div>
      </div>

      {/* Files */}
      <div className="psg-card">
        <div className="psg-card-header">
          <FileCode size={16} />
          <span className="psg-card-title">Files</span>
        </div>
        <div className="psg-card-body">
          <span className="psg-card-value">{allFiles.size}</span>
          <span className="psg-card-detail">unique files across {decomposedCount} directive{decomposedCount !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Complexity */}
      <div className="psg-card">
        <div className="psg-card-header">
          <Layers size={16} />
          <span className="psg-card-title">Complexity</span>
        </div>
        <div className="psg-card-body">
          <span className="psg-card-value">{totalDeps} deps</span>
          <span className="psg-card-detail">{goals.length} directive{goals.length !== 1 ? 's' : ''}</span>
        </div>
      </div>
    </div>
  )
}
