import { Timer, TrendingUp, Clock, CheckCircle2, Zap, BarChart3 } from 'lucide-react'

function formatMs(ms) {
  if (ms == null || ms < 0) return '—'
  const secs = Math.floor(ms / 1000)
  const mins = Math.floor(secs / 60)
  if (mins > 0) return `${mins}m ${secs % 60}s`
  if (secs > 0) return `${secs}s`
  return `${ms}ms`
}

/**
 * Execution timing summary — rollup stats, not per-unit detail.
 * Per-unit timing is shown directly on graph nodes.
 */
export default function ExecutionTimingPanel({ timing }) {
  if (!timing) return null

  const { per_unit = [], throughput, estimated_remaining_ms, active_count, queued_count } = timing
  if (per_unit.length === 0) return null

  // Compute rollup stats from per-unit data
  const completedUnits = per_unit.filter(e => (e.status === 'completed' || e.status === 'verified') && e.exec_duration_ms > 0)
  const failedUnits = per_unit.filter(e => e.status === 'failed')
  const totalUnits = per_unit.length

  const execTimes = completedUnits.map(e => e.exec_duration_ms).filter(Boolean)
  const avgExec = execTimes.length > 0 ? Math.round(execTimes.reduce((a, b) => a + b, 0) / execTimes.length) : null
  const maxExec = execTimes.length > 0 ? Math.max(...execTimes) : null
  const minExec = execTimes.length > 0 ? Math.min(...execTimes) : null
  const totalExec = execTimes.length > 0 ? execTimes.reduce((a, b) => a + b, 0) : null

  const waitTimes = per_unit.map(e => e.queue_wait_ms).filter(w => w != null && w > 0)
  const avgWait = waitTimes.length > 0 ? Math.round(waitTimes.reduce((a, b) => a + b, 0) / waitTimes.length) : null

  return (
    <div className="exec-panel">
      <div className="exec-panel-header">
        <Timer size={14} />
        <span className="exec-panel-title">Timing</span>
        <span className="exec-panel-count">
          {completedUnits.length}/{totalUnits}
        </span>
      </div>

      <div className="ett-stats">
        {active_count > 0 && (
          <div className="ett-stat-row">
            <Zap size={12} className="ett-stat-icon ett-stat-icon--active" />
            <span className="ett-stat-label">Active</span>
            <span className="ett-stat-value">{active_count}</span>
          </div>
        )}
        {queued_count > 0 && (
          <div className="ett-stat-row">
            <Clock size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Queued</span>
            <span className="ett-stat-value">{queued_count}</span>
          </div>
        )}
        {avgExec != null && (
          <div className="ett-stat-row">
            <BarChart3 size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Avg exec</span>
            <span className="ett-stat-value">{formatMs(avgExec)}</span>
          </div>
        )}
        {minExec != null && maxExec != null && minExec !== maxExec && (
          <div className="ett-stat-row">
            <Timer size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Range</span>
            <span className="ett-stat-value">{formatMs(minExec)} — {formatMs(maxExec)}</span>
          </div>
        )}
        {avgWait != null && (
          <div className="ett-stat-row">
            <Clock size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Avg wait</span>
            <span className="ett-stat-value">{formatMs(avgWait)}</span>
          </div>
        )}
        {totalExec != null && (
          <div className="ett-stat-row">
            <CheckCircle2 size={12} className="ett-stat-icon ett-stat-icon--done" />
            <span className="ett-stat-label">Total exec</span>
            <span className="ett-stat-value">{formatMs(totalExec)}</span>
          </div>
        )}
        {estimated_remaining_ms != null && (
          <div className="ett-stat-row">
            <TrendingUp size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Est. remaining</span>
            <span className="ett-stat-value">~{formatMs(estimated_remaining_ms)}</span>
          </div>
        )}
        {failedUnits.length > 0 && (
          <div className="ett-stat-row ett-stat-row--failed">
            <Timer size={12} className="ett-stat-icon" />
            <span className="ett-stat-label">Failed</span>
            <span className="ett-stat-value">{failedUnits.length}</span>
          </div>
        )}
      </div>
    </div>
  )
}
