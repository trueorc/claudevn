import { Clock, GitBranch, CheckCircle2, AlertTriangle, Zap } from 'lucide-react'
import './DecompositionTimeline.css'

const EVENT_CONFIG = {
  'decomposition.started': { icon: GitBranch, label: 'Decomposition started' },
  'decomposition.updated': { icon: Zap, label: 'Work units updated' },
  'decomposition.completed': { icon: CheckCircle2, label: 'Decomposition complete' },
  'decomposition.approved': { icon: CheckCircle2, label: 'Decomposition approved' },
  'decomposition.step_completed': { icon: CheckCircle2, label: 'Pipeline step completed' },
  'decomposition.step_failed': { icon: AlertTriangle, label: 'Pipeline step failed' },
  'coherence.updated': { icon: Zap, label: 'Coherence analysis updated' },
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Chronological feed of decomposition events.
 * Shows recent activity for observability.
 */
export default function DecompositionTimeline({ events = [] }) {
  if (!events || events.length === 0) {
    return (
      <div className="dt">
        <div className="dt-header">
          <Clock size={14} />
          <span className="dt-title">Activity</span>
        </div>
        <p className="dt-empty">No recent activity</p>
      </div>
    )
  }

  // Show most recent first, cap at 20
  const recent = [...events].reverse().slice(0, 20)

  return (
    <div className="dt">
      <div className="dt-header">
        <Clock size={14} />
        <span className="dt-title">Activity</span>
        <span className="dt-count">{events.length}</span>
      </div>
      <div className="dt-list">
        {recent.map((event, i) => {
          const config = EVENT_CONFIG[event.event] || { icon: Zap, label: event.event }
          const Icon = config.icon
          return (
            <div key={i} className="dt-item">
              <Icon size={12} className="dt-item-icon" />
              <span className="dt-item-label">{config.label}</span>
              {event.detail && <span className="dt-item-detail">{event.detail}</span>}
              {event.step_name && <span className="dt-item-detail">{event.step_name}</span>}
              {event.goal_description && <span className="dt-item-detail">{event.goal_description?.slice(0, 40)}</span>}
              <span className="dt-item-time">{formatTime(event.timestamp)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
