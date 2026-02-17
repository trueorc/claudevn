import { User, GitBranch, Clock } from 'lucide-react'
import { StatusBadge } from '../common/Badge'
import Badge from '../common/Badge'
import EmptyState from '../common/EmptyState'
import './ActiveWorkPanel.css'

const priorityColors = {
  P0: 'error',
  P1: 'warning',
  P2: 'default',
  P3: 'info'
}

function ActiveWorkPanel({ items, loading }) {
  if (loading) {
    return (
      <div className="active-work-panel">
        <div className="panel-header">
          <h3 className="panel-title">Active Work</h3>
        </div>
        <div style={{ padding: 'var(--space-lg)', color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
          Loading...
        </div>
      </div>
    )
  }

  if (!items || items.length === 0) {
    return (
      <div className="active-work-panel">
        <div className="panel-header">
          <h3 className="panel-title">Active Work</h3>
        </div>
        <EmptyState
          icon={Clock}
          title="No active work"
          description="Work items in progress will appear here"
        />
      </div>
    )
  }

  return (
    <div className="active-work-panel">
      <div className="panel-header">
        <h3 className="panel-title">Active Work</h3>
        <span className="panel-count">{items.length}</span>
      </div>
      <div className="active-work-list">
        {items.map(item => (
          <div key={item.work_id} className="active-work-item">
            <div className="item-header">
              <h4 className="item-title">{item.title}</h4>
              <StatusBadge status={item.status} />
            </div>
            {item.description && (
              <p className="item-description">{item.description}</p>
            )}
            <div className="item-meta">
              {item.priority && (
                <Badge variant={priorityColors[item.priority] || 'default'}>
                  {item.priority}
                </Badge>
              )}
              {item.assigned_to && (
                <div className="meta-item">
                  <User size={12} />
                  <span>{item.assigned_to}</span>
                </div>
              )}
              {item.branch_name && (
                <div className="meta-item">
                  <GitBranch size={12} />
                  <span>{item.branch_name}</span>
                </div>
              )}
            </div>
            {item.progress_percent !== undefined && (
              <div className="item-progress">
                <div className="item-progress-bar">
                  <div
                    className="item-progress-fill"
                    style={{ width: `${item.progress_percent}%` }}
                  />
                </div>
                <span className="item-progress-text">{item.progress_percent}%</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default ActiveWorkPanel
