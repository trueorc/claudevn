import { NavLink } from 'react-router-dom'
import { Bell } from 'lucide-react'
import useNotifications from '../../hooks/useNotifications'
import './Notifications.css'

function NotificationBell({ projectId }) {
  const { unreadCount } = useNotifications(projectId, { pollInterval: 15000 })

  return (
    <NavLink
      to="/notifications"
      className={({ isActive }) =>
        `notification-bell-trigger ${isActive ? 'active' : ''}`
      }
      title={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}
    >
      <Bell size={16} strokeWidth={1.5} />
      {unreadCount > 0 && (
        <span className="notification-bell-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
      )}
    </NavLink>
  )
}

export default NotificationBell
