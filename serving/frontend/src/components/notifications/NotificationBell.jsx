import { useState, useRef, useEffect } from 'react'
import { Bell, CheckCheck, Info, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react'
import useNotifications from '../../hooks/useNotifications'
import './Notifications.css'

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

function timeAgo(dateStr) {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function NotificationBell({ projectId }) {
  const [isOpen, setIsOpen] = useState(false)
  const [panelPos, setPanelPos] = useState(null)
  const containerRef = useRef(null)
  const bellRef = useRef(null)

  const { notifications, unreadCount, markRead, markAllRead, refresh } =
    useNotifications(projectId, { pollInterval: 15000 })

  // Position panel above the bell
  useEffect(() => {
    if (isOpen && bellRef.current) {
      const rect = bellRef.current.getBoundingClientRect()
      setPanelPos({
        bottom: window.innerHeight - rect.top + 4,
        left: rect.left,
      })
    }
  }, [isOpen])

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Close on Escape
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') setIsOpen(false)
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKey)
      return () => document.removeEventListener('keydown', handleKey)
    }
  }, [isOpen])

  const handleOpen = () => {
    setIsOpen(!isOpen)
    if (!isOpen) refresh()
  }

  return (
    <div className="notification-bell-container" ref={containerRef}>
      <button
        ref={bellRef}
        className="notification-bell-trigger"
        onClick={handleOpen}
        title={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}
      >
        <Bell size={16} strokeWidth={1.5} />
        {unreadCount > 0 && (
          <span className="notification-bell-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      {isOpen && panelPos && (
        <div
          className="notification-panel"
          style={{ bottom: `${panelPos.bottom}px`, left: `${panelPos.left}px` }}
        >
          <div className="notification-panel-header">
            <span className="notification-panel-title">Notifications</span>
            {unreadCount > 0 && (
              <button className="notification-mark-all" onClick={markAllRead} title="Mark all read">
                <CheckCheck size={14} />
              </button>
            )}
          </div>

          <div className="notification-list">
            {notifications.length === 0 ? (
              <div className="notification-empty">No notifications</div>
            ) : (
              notifications.map(n => {
                const Icon = levelIcons[n.level] || Info
                return (
                  <button
                    key={n.notification_id}
                    className={`notification-item ${n.read ? 'read' : 'unread'}`}
                    onClick={() => !n.read && markRead(n.notification_id)}
                  >
                    <Icon size={14} style={{ color: levelColors[n.level], flexShrink: 0 }} />
                    <div className="notification-item-content">
                      <span className="notification-item-title">{n.title}</span>
                      {n.message && (
                        <span className="notification-item-message">{n.message}</span>
                      )}
                      <span className="notification-item-time">{timeAgo(n.created_at)}</span>
                    </div>
                    {!n.read && <span className="notification-unread-dot" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default NotificationBell
