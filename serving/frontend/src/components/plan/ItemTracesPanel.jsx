import { X, GitBranch, Shuffle, Move, AlertTriangle, CheckCircle, UserPlus, Link2, Loader2 } from 'lucide-react'
import useItemTraces from '../../hooks/useItemTraces'
import './Plan.css'

const traceTypeIcons = {
  profile_shift: Shuffle,
  bucket_reorganization: GitBranch,
  task_movement: Move,
  conflict_identified: AlertTriangle,
  conflict_resolved: CheckCircle,
  worker_assignment: UserPlus,
}

const traceTypeLabels = {
  profile_shift: 'Profile Shift',
  bucket_reorganization: 'Reorganization',
  task_movement: 'Task Movement',
  conflict_identified: 'Conflict Found',
  conflict_resolved: 'Conflict Resolved',
  worker_assignment: 'Assignment',
}

function formatTimeAgo(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now - date
  const diffMinutes = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMinutes < 1) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return `${diffDays}d ago`
}

function ItemTracesPanel({ projectId, item, onClose }) {
  const { traces, loading, error } = useItemTraces(projectId, item?.issue_id)
  const displayId = item?.number ? `#${item.number}` : item?.issue_id?.slice(0, 8)

  return (
    <div className="plan-item-traces-panel">
      <div className="plan-item-traces-header">
        <span className="plan-item-traces-title">
          Ordering History for {displayId}
        </span>
        <button className="plan-item-traces-close" onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <div className="plan-item-traces-subtitle">{item?.title}</div>

      <div className="plan-item-traces-content">
        {loading && (
          <div className="plan-item-traces-loading">
            <Loader2 size={16} className="spin" />
            Loading traces...
          </div>
        )}

        {error && (
          <div className="plan-item-traces-error">
            Failed to load traces: {error}
          </div>
        )}

        {!loading && !error && traces.length === 0 && (
          <div className="plan-item-traces-empty">
            No ordering decisions recorded for this item yet.
          </div>
        )}

        {!loading && traces.length > 0 && (
          <div className="plan-why-timeline">
            {traces.map(trace => {
              const Icon = traceTypeIcons[trace.decision_type] || Move
              const typeLabel = traceTypeLabels[trace.decision_type] || trace.decision_type
              return (
                <div key={trace.trace_id} className="plan-trace-card">
                  <div className="plan-trace-time">{formatTimeAgo(trace.timestamp)}</div>
                  <div className="plan-trace-content">
                    <div className="plan-trace-type">
                      <Icon size={14} />
                      <span>{typeLabel}</span>
                      {trace.related_trace_ids?.length > 0 && (
                        <span className="plan-trace-chain-indicator" title="Part of a decision chain">
                          <Link2 size={12} />
                        </span>
                      )}
                    </div>
                    <p className="plan-trace-summary">{trace.decision_summary}</p>
                    {trace.key_factors?.length > 0 && (
                      <ul className="plan-trace-factors">
                        {trace.key_factors.map((factor, i) => (
                          <li key={i}>{factor}</li>
                        ))}
                      </ul>
                    )}
                    {trace.trigger && typeof trace.trigger === 'object' && trace.trigger.description && (
                      <p className="plan-trace-trigger">{trace.trigger.description}</p>
                    )}
                    {trace.trigger && typeof trace.trigger === 'string' && (
                      <p className="plan-trace-trigger">{trace.trigger}</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default ItemTracesPanel
