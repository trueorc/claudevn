import { AlertTriangle, CheckCircle2, Gauge, Settings, Zap } from 'lucide-react'
import './AttentionBanner.css'

const TYPE_CONFIG = {
  approval: { icon: CheckCircle2, className: 'ab-item--approval', label: 'Needs Approval' },
  low_confidence: { icon: Gauge, className: 'ab-item--warning', label: 'Low Confidence' },
  coherence: { icon: AlertTriangle, className: 'ab-item--warning', label: 'Coherence Issue' },
  plan_conflict: { icon: AlertTriangle, className: 'ab-item--warning', label: 'Plan Conflict' },
  env_approval: { icon: Settings, className: 'ab-item--info', label: 'Environment' },
}

/**
 * Top-of-page banner showing items that need user attention.
 * Each item links to the relevant directive.
 */
export default function AttentionBanner({ items = [], onSelectGoal }) {
  if (!items || items.length === 0) return null

  return (
    <div className="ab">
      <div className="ab-header">
        <Zap size={14} />
        <span className="ab-title">Needs Attention</span>
        <span className="ab-count">{items.length}</span>
      </div>
      <div className="ab-items">
        {items.map((item, i) => {
          const config = TYPE_CONFIG[item.type] || TYPE_CONFIG.approval
          const Icon = config.icon
          return (
            <button
              key={i}
              className={`ab-item ${config.className}`}
              onClick={() => item.goalId && onSelectGoal?.({ goal_id: item.goalId, title: item.title })}
            >
              <Icon size={14} />
              <div className="ab-item-text">
                <span className="ab-item-label">{config.label}</span>
                <span className="ab-item-detail">{item.detail}</span>
              </div>
              {item.goalId && <span className="ab-item-arrow">View</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
