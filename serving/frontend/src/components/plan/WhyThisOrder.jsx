import { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight, GitBranch, Shuffle, Move, AlertTriangle, CheckCircle, UserPlus, Layers, Link2 } from 'lucide-react'
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

// Ordering-relevant trace types (shown prominently)
const ORDERING_TYPES = new Set([
  'profile_shift',
  'bucket_reorganization',
  'task_movement',
])

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

function WhyThisOrder({ buckets = [], traces = [], traceCount = 0, onTraceChainClick }) {
  const [orderingExpanded, setOrderingExpanded] = useState(true)
  const [otherExpanded, setOtherExpanded] = useState(false)
  const hasBuckets = buckets.length > 0

  // Split traces into ordering-relevant and other
  const { orderingTraces, otherTraces } = useMemo(() => {
    const ordering = []
    const other = []
    for (const trace of traces) {
      if (ORDERING_TYPES.has(trace.decision_type)) {
        ordering.push(trace)
      } else {
        other.push(trace)
      }
    }
    return { orderingTraces: ordering, otherTraces: other }
  }, [traces])

  const hasOrderingTraces = orderingTraces.length > 0
  const hasOtherTraces = otherTraces.length > 0

  if (!hasBuckets && !hasOrderingTraces && !hasOtherTraces) return null

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

      {hasOrderingTraces && (
        <>
          <button
            className="plan-why-header"
            onClick={() => setOrderingExpanded(!orderingExpanded)}
          >
            {orderingExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span className="plan-why-title">Ordering Decisions</span>
            <span className="plan-why-count">
              {orderingTraces.length} decision{orderingTraces.length !== 1 ? 's' : ''}
            </span>
          </button>
          {orderingExpanded && (
            <div className="plan-why-timeline">
              {orderingTraces.map(trace => (
                <TraceCard
                  key={trace.trace_id}
                  trace={trace}
                  onChainClick={onTraceChainClick}
                />
              ))}
            </div>
          )}
        </>
      )}

      {hasOtherTraces && (
        <>
          <button
            className="plan-why-header plan-why-header--secondary"
            onClick={() => setOtherExpanded(!otherExpanded)}
          >
            {otherExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span className="plan-why-title">Other Activity</span>
            <span className="plan-why-count">
              {otherTraces.length}
            </span>
          </button>
          {otherExpanded && (
            <div className="plan-why-timeline">
              {otherTraces.map(trace => (
                <TraceCard key={trace.trace_id} trace={trace} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function TraceCard({ trace, onChainClick }) {
  const { decision_type, decision_summary, timestamp, trigger, key_factors, related_trace_ids } = trace
  const Icon = traceTypeIcons[decision_type] || Move
  const typeLabel = traceTypeLabels[decision_type] || decision_type
  const hasChain = related_trace_ids && related_trace_ids.length > 0

  return (
    <div className="plan-trace-card">
      <div className="plan-trace-time">{formatTimeAgo(timestamp)}</div>
      <div className="plan-trace-content">
        <div className="plan-trace-type">
          <Icon size={14} />
          <span>{typeLabel}</span>
          {hasChain && onChainClick && (
            <button
              className="plan-trace-chain-link"
              onClick={(e) => {
                e.stopPropagation()
                onChainClick(trace.trace_id)
              }}
              title="View related decisions"
            >
              <Link2 size={12} />
            </button>
          )}
        </div>
        <p className="plan-trace-summary">{decision_summary}</p>
        {key_factors && key_factors.length > 0 && (
          <ul className="plan-trace-factors">
            {key_factors.map((factor, i) => (
              <li key={i}>{factor}</li>
            ))}
          </ul>
        )}
        {trigger && typeof trigger === 'string' && (
          <p className="plan-trace-trigger">{trigger}</p>
        )}
        {trigger && typeof trigger === 'object' && trigger.description && (
          <p className="plan-trace-trigger">{trigger.description}</p>
        )}
      </div>
    </div>
  )
}

export default WhyThisOrder
