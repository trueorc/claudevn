import './UserAvatar.css'

// Deterministic color palette based on user_id hash
const AVATAR_COLORS = [
  '#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#84cc16', '#f97316', '#ec4899',
  '#6366f1', '#14b8a6', '#eab308', '#e11d48', '#0ea5e9',
]

function hashCode(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

function getAvatarColor(userId) {
  return AVATAR_COLORS[hashCode(userId || '') % AVATAR_COLORS.length]
}

function getInitials(displayName) {
  if (!displayName) return '?'
  const parts = displayName.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }
  return parts[0].substring(0, 2).toUpperCase()
}

function UserAvatar({ userId, displayName, size = 'md', showStatus, status }) {
  const color = getAvatarColor(userId)
  const initials = getInitials(displayName || userId)

  return (
    <div
      className={`user-avatar user-avatar-${size}`}
      style={{ backgroundColor: color }}
      title={displayName || userId}
      role="img"
      aria-label={displayName || userId || 'User'}
    >
      <span className="user-avatar-initials">{initials}</span>
      {showStatus && (
        <span className={`user-avatar-status user-avatar-status-${status || 'offline'}`} />
      )}
    </div>
  )
}

export default UserAvatar
export { getAvatarColor, getInitials }
