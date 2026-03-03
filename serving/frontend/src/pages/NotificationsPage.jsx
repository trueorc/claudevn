import { useState, useMemo } from 'react'
import { Bell, CheckCheck, Trash2, Info, CheckCircle2, AlertTriangle, AlertCircle, X, Filter } from 'lucide-react'
import useNotifications from '../hooks/useNotifications'
import { useProjectContext } from '../contexts/ProjectContext'
import './NotificationsPage.css'

const levelIcons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
}

const levelColors = {
  info: 'var(--primary)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--error)',
}

const categoryLabels = {
  goal: 'Goal',
  issue: 'Issue',
  work: 'Work',
  compute: 'Compute',
  system: 'System',
}

const readFilters = [
  { value: 'all', label: 'All' },
  { value: 'unread', label: 'Unread' },
  { value: 'read', label: 'Read' },
]

const categoryFilters = [
  { value: '', label: 'All Types' },
  { value: 'goal', label: 'Goal' },
  { value: 'issue', label: 'Issue' },
  { value: 'work', label: 'Work' },
  { value: 'compute', label: 'Compute' },
  { value: 'system', label: 'System' },
]

function timeAgo(dateStr) {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function groupByDate(notifications) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  const groups = { Today: [], Yesterday: [], Older: [] }

  for (const n of notifications) {
    const date = new Date(n.created_at)
    date.setHours(0, 0, 0, 0)
    if (date.getTime() >= today.getTime()) {
      groups.Today.push(n)
    } else if (date.getTime() >= yesterday.getTime()) {
      groups.Yesterday.push(n)
    } else {
      groups.Older.push(n)
    }
  }

  return Object.entries(groups).filter(([, items]) => items.length > 0)
}

function NotificationsPage() {
  const { activeProject } = useProjectContext()
  const [readFilter, setReadFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('')

  const {
    notifications,
    unreadCount,
    loading,
    markRead,
    markAllRead,
    dismiss,
    dismissAll,
  } = useNotifications(activeProject?.project_id, { pollInterval: 15000 })

  const filtered = useMemo(() => {
    let items = notifications
    if (readFilter === 'unread') items = items.filter(n => !n.read)
    if (readFilter === 'read') items = items.filter(n => n.read)
    if (categoryFilter) items = items.filter(n => n.category === categoryFilter)
    return items
  }, [notifications, readFilter, categoryFilter])

  const grouped = useMemo(() => groupByDate(filtered), [filtered])

  const hasReadNotifications = notifications.some(n => n.read)

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">Notifications</h1>
        <div className="notif-page-actions">
          {unreadCount > 0 && (
            <button className="notif-action-btn" onClick={markAllRead} title="Mark all as read">
              <CheckCheck size={14} />
              <span>Mark all read</span>
            </button>
          )}
          {hasReadNotifications && (
            <button className="notif-action-btn notif-action-danger" onClick={dismissAll} title="Dismiss all read">
              <Trash2 size={14} />
              <span>Dismiss read</span>
            </button>
          )}
        </div>
      </header>

      <div className="notif-toolbar">
        <div className="notif-filters">
          <div className="notif-filter-group">
            {readFilters.map(f => (
              <button
                key={f.value}
                className={`notif-filter-btn ${readFilter === f.value ? 'active' : ''}`}
                onClick={() => setReadFilter(f.value)}
              >
                {f.label}
                {f.value === 'unread' && unreadCount > 0 && (
                  <span className="notif-filter-count">{unreadCount}</span>
                )}
              </button>
            ))}
          </div>
          <div className="notif-filter-sep" />
          <div className="notif-category-filter">
            <Filter size={12} />
            <select
              value={categoryFilter}
              onChange={e => setCategoryFilter(e.target.value)}
              className="notif-category-select"
            >
              {categoryFilters.map(f => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {loading && notifications.length === 0 ? (
        <div className="notif-empty">
          <div className="notif-empty-icon"><Bell size={32} /></div>
          <p>Loading notifications...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="notif-empty">
          <div className="notif-empty-icon"><Bell size={32} /></div>
          <p className="notif-empty-title">
            {readFilter === 'unread' ? 'No unread notifications' :
             readFilter === 'read' ? 'No read notifications' :
             'No notifications yet'}
          </p>
          <p className="notif-empty-sub">
            {readFilter === 'all'
              ? 'System events will appear here as they happen.'
              : 'Try changing the filter to see more.'}
          </p>
        </div>
      ) : (
        <div className="notif-list">
          {grouped.map(([label, items]) => (
            <div key={label} className="notif-group">
              <div className="notif-group-label">{label}</div>
              {items.map(n => {
                const Icon = levelIcons[n.level] || Info
                return (
                  <div
                    key={n.notification_id}
                    className={`notif-card ${n.read ? 'read' : 'unread'}`}
                  >
                    <div className="notif-card-icon" style={{ color: levelColors[n.level] }}>
                      <Icon size={16} />
                    </div>
                    <div className="notif-card-body">
                      <div className="notif-card-header">
                        <span className="notif-card-title">{n.title}</span>
                        <span className="notif-card-time">{timeAgo(n.created_at)}</span>
                      </div>
                      {n.message && <p className="notif-card-message">{n.message}</p>}
                      <div className="notif-card-meta">
                        {n.category && (
                          <span className="notif-card-category">
                            {categoryLabels[n.category] || n.category}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="notif-card-actions">
                      {!n.read && (
                        <button
                          className="notif-card-action"
                          onClick={() => markRead(n.notification_id)}
                          title="Mark as read"
                        >
                          <CheckCheck size={14} />
                        </button>
                      )}
                      <button
                        className="notif-card-action notif-card-dismiss"
                        onClick={() => dismiss(n.notification_id)}
                        title="Dismiss"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default NotificationsPage
