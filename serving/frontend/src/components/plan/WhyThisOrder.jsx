import { useState } from 'react'
import { ChevronDown, ChevronRight, GitBranch, Shuffle, Move, AlertTriangle, CheckCircle, UserPlus, Layers } from 'lucide-react'
import '../common/BucketBadges.css'
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

function WhyThisOrder({ buckets = [], traces = [], traceCount = 0 }) {
  const [tracesExpanded, setTracesExpanded] = useState(false)
  const hasBuckets = buckets.length > 0
  const hasTraces = traces.length > 0

  if (!hasBuckets && !hasTraces) return null

  const sortedBuckets = hasBuckets
    ? buckets.slice().sort((a, b) => a.rank - b.rank)
    : []

  return (
    <div className="plan-why-section">
      <div className="plan-ordering-header">
        <Layers size={16} />
        <span className="plan-ordering-title">Execution Order</span>
      </div>

      {hasBuckets ? (
        <div className="plan-ordering-content">
          <p className="plan-ordering-explanation">
            Items are ordered by bucket rank (highest priority bucket first), then by intra-bucket priority.
          </p>
          <div className="plan-bucket-sequence">
            {sortedBuckets.map(bucket => {
              const name = bucket.definition?.name || bucket.bucket_id
              const description = bucket.definition?.description || ''
              const itemCount = bucket.items?.length || 0
              return (
                <div key={bucket.bucket_id} className="plan-bucket-row">
                  <span className={`plan-bucket-rank bucket-badge-rank-${Math.min(bucket.rank, 3)}`}>
                    #{bucket.rank}
                  </span>
                  <span className="plan-bucket-name" title={description}>
                    {name}
                  </span>
                  {description && (
                    <span className="plan-bucket-desc">{description}</span>
                  )}
                  <span className="plan-bucket-count">
                    {itemCount} item{itemCount !== 1 ? 's' : ''}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="plan-ordering-content">
          <p className="plan-ordering-explanation">
            No bucket tree defined. Items are ordered by priority.
          </p>
        </div>
      )}

      {hasTraces && (
        <>
          <button
            className="plan-why-header"
            onClick={() => setTracesExpanded(!tracesExpanded)}
          >
            {tracesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span className="plan-why-title">Recent Decisions</span>
            <span className="plan-why-count">{traceCount} decision{traceCount !== 1 ? 's' : ''}</span>
          </button>
          {tracesExpanded && (
            <div className="plan-why-timeline">
              {traces.map(trace => (
                <TraceCard key={trace.trace_id} trace={trace} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function TraceCard({ trace }) {
  const { decision_type, decision_summary, timestamp, trigger } = trace
  const Icon = traceTypeIcons[decision_type] || Move
  const typeLabel = traceTypeLabels[decision_type] || decision_type

  return (
    <div className="plan-trace-card">
      <div className="plan-trace-time">{formatTimeAgo(timestamp)}</div>
      <div className="plan-trace-content">
        <div className="plan-trace-type">
          <Icon size={14} />
          <span>{typeLabel}</span>
        </div>
        <p className="plan-trace-summary">{decision_summary}</p>
        {trigger && (
          <p className="plan-trace-trigger">{trigger}</p>
        )}
      </div>
    </div>
  )
}

export default WhyThisOrder
