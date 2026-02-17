import { useState } from 'react'
import { ChevronDown, ChevronRight, GitBranch, Shuffle, Move, AlertTriangle, CheckCircle, UserPlus } from 'lucide-react'
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

function WhyThisOrder({ traces = [], traceCount = 0 }) {
  const [expanded, setExpanded] = useState(false)

  if (traces.length === 0) return null

  return (
    <div className="plan-why-section">
      <button
        className="plan-why-header"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="plan-why-title">Why this order</span>
        <span className="plan-why-count">{traceCount} decision{traceCount !== 1 ? 's' : ''}</span>
      </button>
      {expanded && (
        <div className="plan-why-timeline">
          {traces.map(trace => (
            <TraceCard key={trace.trace_id} trace={trace} />
          ))}
        </div>
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
