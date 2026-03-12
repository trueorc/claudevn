import './Badge.css'

function Badge({ variant = 'default', children }) {
  return (
    <span className={`badge badge-${variant}`}>
      {children}
    </span>
  )
}

export function StatusBadge({ status }) {
  const variants = {
    online: 'success',
    healthy: 'success',
    running: 'success',
    completed: 'success',
    done: 'success',
    implemented: 'warning',
    degraded: 'warning',
    draining: 'warning',
    benched: 'warning',
    pending: 'info',
    assigned: 'info',
    in_progress: 'info',
    offline: 'error',
    error: 'error',
    failed: 'error',
    blocked: 'error'
  }

  const variant = variants[status?.toLowerCase()] || 'default'

  return (
    <Badge variant={variant}>
      {status?.replace(/_/g, ' ')}
    </Badge>
  )
}

export default Badge
