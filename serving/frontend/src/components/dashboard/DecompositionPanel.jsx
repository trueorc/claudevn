import { useNavigate } from 'react-router-dom'
import { GitBranch, ChevronRight, AlertCircle, CheckCircle2, Clock, Pencil } from 'lucide-react'
import './DecompositionPanel.css'

const STATUS_CONFIG = {
  draft: { icon: Pencil, label: 'Draft', className: 'dp-status--draft' },
  approved: { icon: CheckCircle2, label: 'Approved', className: 'dp-status--approved' },
  executing: { icon: Clock, label: 'Executing', className: 'dp-status--executing' },
  needs_review: { icon: AlertCircle, label: 'Needs Review', className: 'dp-status--review' },
}

function DecompositionItem({ goal }) {
  const navigate = useNavigate()
  const statusInfo = STATUS_CONFIG[goal.decomposition_status] || STATUS_CONFIG.draft
  const StatusIcon = statusInfo.icon

  return (
    <button
      className="dp-item"
      onClick={() => navigate(`/plan?goal=${goal.goal_id}`)}
    >
      <div className="dp-item-header">
        <GitBranch size={14} className="dp-item-icon" />
        <span className="dp-item-title">{goal.title || goal.description?.slice(0, 60)}</span>
        <ChevronRight size={14} className="dp-item-chevron" />
      </div>
      <div className="dp-item-meta">
        <span className={`dp-status ${statusInfo.className}`}>
          <StatusIcon size={12} />
          {statusInfo.label}
        </span>
        {goal.work_unit_count > 0 && (
          <span className="dp-unit-count">{goal.work_unit_count} units</span>
        )}
      </div>
    </button>
  )
}

/**
 * Layer 1 panel — shows active decompositions and their status.
 * Quick links into the decomposition page for review.
 */
export default function DecompositionPanel({ goals = [] }) {
  const navigate = useNavigate()
  const activeGoals = goals.filter(g =>
    g.decomposition_status && g.decomposition_status !== 'completed'
  )

  return (
    <div className="dp-panel">
      <div className="dp-panel-header">
        <span className="dp-panel-title">Decomposition</span>
        <span className="dp-panel-badge">{activeGoals.length}</span>
      </div>

      {activeGoals.length === 0 ? (
        <p className="dp-empty">No active decompositions</p>
      ) : (
        <div className="dp-list">
          {activeGoals.slice(0, 5).map((goal) => (
            <DecompositionItem key={goal.goal_id} goal={goal} />
          ))}
        </div>
      )}

      <button className="dp-view-all" onClick={() => navigate('/plan')}>
        View all directives
        <ChevronRight size={14} />
      </button>
    </div>
  )
}
