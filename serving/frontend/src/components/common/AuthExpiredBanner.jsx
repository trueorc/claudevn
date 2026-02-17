import { AlertTriangle } from 'lucide-react'
import './AuthExpiredBanner.css'

function AuthExpiredBanner({ expired, expiringAt, onReauth }) {
  // Calculate days until expiry if expiringAt is provided
  let daysUntilExpiry = null
  let isExpiringSoon = false

  if (expiringAt && !expired) {
    const expiryDate = new Date(expiringAt)
    const now = new Date()
    const diffMs = expiryDate - now
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays <= 7 && diffDays >= 0) {
      daysUntilExpiry = diffDays
      isExpiringSoon = true
    }
  }

  // Determine banner state
  const isExpired = expired
  const bannerClass = isExpired ? 'auth-expired-banner expired' : 'auth-expired-banner expiring'

  if (isExpired) {
    return (
      <div className={bannerClass}>
        <AlertTriangle size={18} className="auth-expired-icon" />
        <span className="auth-expired-message">
          Token expired — click to re-authenticate
        </span>
        <button className="auth-expired-btn" onClick={onReauth}>
          Re-authenticate
        </button>
      </div>
    )
  }

  if (isExpiringSoon) {
    const dayText = daysUntilExpiry === 1 ? 'day' : 'days'
    return (
      <div className={bannerClass}>
        <AlertTriangle size={18} className="auth-expired-icon" />
        <span className="auth-expired-message">
          Token expires in {daysUntilExpiry} {dayText} — re-authenticate to extend
        </span>
        <button className="auth-expired-btn" onClick={onReauth}>
          Re-authenticate
        </button>
      </div>
    )
  }

  return null
}

export default AuthExpiredBanner
