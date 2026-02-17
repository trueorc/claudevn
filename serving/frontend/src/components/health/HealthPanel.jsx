import { CheckCircle, AlertCircle, XCircle, HelpCircle } from 'lucide-react'
import './HealthPanel.css'

const statusConfig = {
  healthy: { icon: CheckCircle, color: 'success', label: 'Healthy' },
  online: { icon: CheckCircle, color: 'success', label: 'Online' },
  connected: { icon: CheckCircle, color: 'success', label: 'Connected' },
  running: { icon: CheckCircle, color: 'success', label: 'Running' },
  degraded: { icon: AlertCircle, color: 'warning', label: 'Degraded' },
  offline: { icon: XCircle, color: 'error', label: 'Offline' },
  unavailable: { icon: XCircle, color: 'error', label: 'Unavailable' },
  unknown: { icon: HelpCircle, color: 'muted', label: 'Unknown' }
}

function HealthPanel({ title, icon: Icon, status, metrics, children, compact = false }) {
  const config = statusConfig[status] || statusConfig.unknown
  const StatusIcon = config.icon

  return (
    <div className={`health-panel health-panel-${config.color}${compact ? ' health-panel-compact' : ''}`}>
      <div className="health-panel-header">
        <div className="health-panel-title">
          {Icon && <Icon size={18} className="health-panel-icon" />}
          <h3>{title}</h3>
        </div>
        <div className={`health-status-indicator health-status-${config.color}`}>
          <StatusIcon size={14} />
          <span>{config.label}</span>
        </div>
      </div>

      {metrics && metrics.length > 0 && (
        <div className="health-metrics">
          {metrics.map((metric, index) => {
            const metricClass = `health-metric${metric.onClick ? ' health-metric-clickable' : ''}${metric.status ? ` health-metric-${metric.status}` : ''}`
            return (
              <div key={index} className={metricClass} onClick={metric.onClick || undefined}>
                <span className="health-metric-value">{metric.value}</span>
                <span className="health-metric-label">{metric.label}</span>
              </div>
            )
          })}
        </div>
      )}

      {children && (
        <div className="health-panel-content">
          {children}
        </div>
      )}
    </div>
  )
}

export function HealthStatusBar({ items }) {
  const total = items.reduce((sum, item) => sum + item.count, 0)
  if (total === 0) return null

  return (
    <div className="health-status-bar">
      {items.map((item, index) => {
        const width = (item.count / total) * 100
        if (width === 0) return null
        return (
          <div
            key={index}
            className={`health-status-segment health-status-${item.color}`}
            style={{ width: `${width}%` }}
            title={`${item.label}: ${item.count}`}
          />
        )
      })}
    </div>
  )
}

export function HealthBreakdown({ items }) {
  return (
    <div className="health-breakdown">
      {items.map((item, index) => (
        <div key={index} className="health-breakdown-item">
          <span className={`health-breakdown-dot health-dot-${item.color}`} />
          <span className="health-breakdown-label">{item.label}</span>
          <span className="health-breakdown-count">{item.count}</span>
        </div>
      ))}
    </div>
  )
}

export default HealthPanel
