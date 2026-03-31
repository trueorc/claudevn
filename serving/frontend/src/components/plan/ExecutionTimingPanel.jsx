import { Timer, TrendingUp, Clock } from 'lucide-react'

function formatMs(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  const secs = Math.floor(ms / 1000)
  const mins = Math.floor(secs / 60)
  if (mins > 0) return `${mins}m ${secs % 60}s`
  return `${secs}s`
}

/**
 * Execution timing metrics — throughput, estimated remaining.
 */
export default function ExecutionTimingPanel({ timing }) {
  if (!timing) return null

  return (
    <div className="exec-panel">
      <div className="exec-panel-header">
        <Timer size={14} />
        <span className="exec-panel-title">Timing</span>
      </div>
      <div className="exec-timing-grid">
        <div className="exec-timing-stat">
          <TrendingUp size={12} />
          <span className="exec-timing-value">{timing.active_count}</span>
          <span className="exec-timing-label">Active</span>
        </div>
        <div className="exec-timing-stat">
          <Clock size={12} />
          <span className="exec-timing-value">{timing.queued_count}</span>
          <span className="exec-timing-label">Queued</span>
        </div>
        <div className="exec-timing-stat">
          <Timer size={12} />
          <span className="exec-timing-value">{timing.pending_count}</span>
          <span className="exec-timing-label">Waiting</span>
        </div>
        {timing.estimated_remaining_ms != null && (
          <div className="exec-timing-stat">
            <Clock size={12} />
            <span className="exec-timing-value">{formatMs(timing.estimated_remaining_ms)}</span>
            <span className="exec-timing-label">Est. Remaining</span>
          </div>
        )}
      </div>
    </div>
  )
}
