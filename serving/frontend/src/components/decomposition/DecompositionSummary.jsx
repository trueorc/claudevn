import { AlertTriangle, CheckCircle2, FileCode, GitBranch, Shield, Layers, Activity } from 'lucide-react'
import './DecompositionSummary.css'

/**
 * Top-level decomposition quality summary.
 * Shows independence audit, verification readiness, and complexity at a glance.
 */
export default function DecompositionSummary({ units = [] }) {
  if (units.length === 0) return null

  // Independence
  const overlaps = units.filter(u => u.independence?.shares_files_with?.length > 0)
  const independenceOk = overlaps.length === 0

  // Verification readiness
  const unitsWithChecks = units.filter(u => u.verification_criteria?.automated?.length > 0)
  const verificationReady = unitsWithChecks.length === units.length
  const totalChecks = units.reduce((sum, u) => sum + (u.verification_criteria?.automated?.length || 0), 0)

  // Complexity
  const totalFiles = new Set(units.flatMap(u => u.formal_spec?.target_files || [])).size
  const totalDeps = units.reduce((sum, u) => sum + (u.independence?.depends_on?.length || 0), 0)
  const maxDepth = computeMaxDepth(units)

  // Status breakdown
  const statusCounts = {}
  units.forEach(u => {
    statusCounts[u.status] = (statusCounts[u.status] || 0) + 1
  })

  return (
    <div className="ds-grid">
      {/* Independence */}
      <div className={`ds-card ${independenceOk ? 'ds-card--ok' : 'ds-card--warn'}`}>
        <div className="ds-card-header">
          {independenceOk ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span className="ds-card-title">Independence</span>
        </div>
        <div className="ds-card-body">
          {independenceOk ? (
            <span className="ds-card-value ds-value--ok">Clean</span>
          ) : (
            <span className="ds-card-value ds-value--warn">{overlaps.length} overlap{overlaps.length !== 1 ? 's' : ''}</span>
          )}
          <span className="ds-card-detail">{units.length} units, no shared files{!independenceOk ? ' — review needed' : ''}</span>
        </div>
      </div>

      {/* Verification Readiness */}
      <div className={`ds-card ${verificationReady ? 'ds-card--ok' : 'ds-card--info'}`}>
        <div className="ds-card-header">
          <Shield size={16} />
          <span className="ds-card-title">Verification</span>
        </div>
        <div className="ds-card-body">
          <span className="ds-card-value">{totalChecks} checks</span>
          <span className="ds-card-detail">
            {unitsWithChecks.length}/{units.length} units covered
            {!verificationReady && ` — ${units.length - unitsWithChecks.length} missing`}
          </span>
        </div>
      </div>

      {/* Complexity */}
      <div className="ds-card">
        <div className="ds-card-header">
          <Layers size={16} />
          <span className="ds-card-title">Complexity</span>
        </div>
        <div className="ds-card-body">
          <span className="ds-card-value">{totalFiles} files</span>
          <span className="ds-card-detail">
            {totalDeps} deps, depth {maxDepth}
          </span>
        </div>
      </div>

      {/* Status */}
      <div className="ds-card">
        <div className="ds-card-header">
          <Activity size={16} />
          <span className="ds-card-title">Status</span>
        </div>
        <div className="ds-card-body">
          <div className="ds-status-pills">
            {Object.entries(statusCounts).map(([status, count]) => (
              <span key={status} className={`ds-status-pill ds-status--${status}`}>
                {count} {status}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function computeMaxDepth(units) {
  const depMap = {}
  units.forEach(u => { depMap[u.id] = u.independence?.depends_on || [] })
  const memo = {}

  function depth(id) {
    if (memo[id] !== undefined) return memo[id]
    const deps = depMap[id] || []
    if (deps.length === 0) { memo[id] = 0; return 0 }
    memo[id] = 1 + Math.max(...deps.map(d => depMap[d] ? depth(d) : 0))
    return memo[id]
  }

  let max = 0
  for (const id of Object.keys(depMap)) {
    max = Math.max(max, depth(id))
  }
  return max
}
