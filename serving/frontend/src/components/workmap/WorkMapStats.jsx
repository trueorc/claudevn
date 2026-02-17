import { CheckCircle2, Clock, AlertCircle, Circle } from 'lucide-react'
import './WorkMapStats.css'

function WorkMapStats({ stats, loading }) {
  if (loading || !stats) {
    return null
  }

  const total = stats.total || 0
  const completed = stats.completed || 0
  const inProgress = stats.in_progress || 0
  const blocked = stats.blocked || 0
  const ready = stats.ready || 0

  const completionPercent = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="workmap-stats">
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon stat-icon-total">
            <Circle size={16} />
          </div>
          <div className="stat-content">
            <div className="stat-label">Total Issues</div>
            <div className="stat-value">{total}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon stat-icon-ready">
            <CheckCircle2 size={16} />
          </div>
          <div className="stat-content">
            <div className="stat-label">Ready</div>
            <div className="stat-value">{ready}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon stat-icon-progress">
            <Clock size={16} />
          </div>
          <div className="stat-content">
            <div className="stat-label">In Progress</div>
            <div className="stat-value">{inProgress}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon stat-icon-blocked">
            <AlertCircle size={16} />
          </div>
          <div className="stat-content">
            <div className="stat-label">Blocked</div>
            <div className="stat-value">{blocked}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon stat-icon-done">
            <CheckCircle2 size={16} />
          </div>
          <div className="stat-content">
            <div className="stat-label">Completed</div>
            <div className="stat-value">{completed}</div>
          </div>
        </div>
      </div>

      <div className="progress-section">
        <div className="progress-header">
          <span className="progress-label">Overall Progress</span>
          <span className="progress-percent">{completionPercent}%</span>
        </div>
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${completionPercent}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export default WorkMapStats
