import { Shield, ShieldCheck, ShieldAlert, ShieldX } from 'lucide-react'
import '../auth/AuthModal.css'

/**
 * Auth status badge for component cards.
 *
 * @param {object} props
 * @param {object} props.authInfo - Auth info from useAuthTokens.getComponentAuth()
 * @param {function} props.onClick - Click handler (opens auth modal)
 */
function AuthBadge({ authInfo, onClick }) {
  if (!authInfo) return null

  const { status, isExpiringSoon, expires_at } = authInfo

  let icon, label, className
  if (status === 'active' && !isExpiringSoon) {
    icon = <ShieldCheck size={12} />
    label = 'Authorized'
    className = 'auth-badge auth-badge-authorized'
  } else if (status === 'active' && isExpiringSoon) {
    icon = <ShieldAlert size={12} />
    label = 'Expiring'
    className = 'auth-badge auth-badge-expiring'
  } else if (status === 'expired') {
    icon = <ShieldX size={12} />
    label = 'Expired'
    className = 'auth-badge auth-badge-expired'
  } else {
    icon = <Shield size={12} />
    label = 'Unauthorized'
    className = 'auth-badge auth-badge-unauthorized'
  }

  const handleClick = (e) => {
    e.stopPropagation()
    if (onClick) onClick()
  }

  return (
    <span className={className} onClick={handleClick} title={expires_at ? `Expires: ${new Date(expires_at).toLocaleDateString()}` : undefined}>
      {icon}
      {label}
    </span>
  )
}

export default AuthBadge
