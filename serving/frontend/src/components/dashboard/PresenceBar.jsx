import { useState } from 'react'
import UserAvatar from '../common/UserAvatar'
import './PresenceBar.css'

function statusToAvatar(status) {
  if (status === 'online') return 'online'
  if (status === 'idle') return 'away'
  return 'offline'
}

function activityLabel(user) {
  const parts = []
  if (user.project_name) parts.push(user.project_name)
  if (user.current_view) parts.push(user.current_view)
  return parts.length > 0 ? parts.join(' · ') : null
}

function PresenceTooltip({ user }) {
  const label = activityLabel(user)
  const view = label ? `viewing ${label}` : user.status
  return (
    <div className="presence-tooltip">
      <span className="presence-tooltip-name">{user.display_name}</span>
      <span className="presence-tooltip-view">{view}</span>
    </div>
  )
}

function PresenceAvatar({ user }) {
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <div
      className="presence-avatar-wrapper"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <UserAvatar
        userId={user.user_id}
        displayName={user.display_name}
        size="sm"
        showStatus
        status={statusToAvatar(user.status)}
      />
      {showTooltip && <PresenceTooltip user={user} />}
    </div>
  )
}

/**
 * PresenceBar — shows avatar circles for online/idle users in the project.
 *
 * @param {{ users: Array }} props
 */
function PresenceBar({ users = [] }) {
  if (users.length === 0) return null

  return (
    <div className="presence-bar" aria-label="Active users">
      {users.map((user) => (
        <PresenceAvatar key={user.user_id} user={user} />
      ))}
    </div>
  )
}

export default PresenceBar
