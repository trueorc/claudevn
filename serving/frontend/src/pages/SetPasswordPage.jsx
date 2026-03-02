import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCognitoAuth } from '../contexts/CognitoAuthContext'
import './LoginPage.css'

export default function SetPasswordPage() {
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  const { completeNewPassword, challengeName } = useCognitoAuth()

  // If no challenge is active, redirect to login
  if (challengeName !== 'NEW_PASSWORD_REQUIRED') {
    navigate('/login', { replace: true })
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setSubmitting(true)
    setError(null)

    const result = await completeNewPassword(newPassword)
    setSubmitting(false)

    if (result.success) {
      navigate('/')
      return
    }

    setError(result.error || 'Failed to set password')
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <h1>Set New Password</h1>
          <p className="login-subtitle">
            Your temporary password has expired. Please set a new password.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="login-error" role="alert">
              <p>{error}</p>
            </div>
          )}

          <div className="login-field">
            <label htmlFor="new-password">New Password</label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Minimum 8 characters"
              disabled={submitting}
              autoFocus
              autoComplete="new-password"
            />
          </div>

          <div className="login-field">
            <label htmlFor="confirm-password">Confirm Password</label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter password"
              disabled={submitting}
              autoComplete="new-password"
            />
          </div>

          <button
            type="submit"
            className="login-submit"
            disabled={!newPassword || !confirmPassword || submitting}
          >
            {submitting ? 'Setting password...' : 'Set password'}
          </button>
        </form>
      </div>
    </div>
  )
}
