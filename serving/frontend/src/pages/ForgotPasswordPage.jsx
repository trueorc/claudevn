import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/auth/AuthContext'
import './LoginPage.css'

export default function ForgotPasswordPage() {
  const [step, setStep] = useState(1) // 1=email, 2=code+password
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)
  const navigate = useNavigate()
  const { forgotPassword, confirmForgotPassword } = useAuth()

  async function handleSendCode(e) {
    e.preventDefault()
    if (!email) return

    setSubmitting(true)
    setError(null)

    const result = await forgotPassword(email)
    setSubmitting(false)

    if (result.success) {
      setStep(2)
      return
    }

    setError(result.error || 'Failed to send reset code')
  }

  async function handleResetPassword(e) {
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

    const result = await confirmForgotPassword(email, code, newPassword)
    setSubmitting(false)

    if (result.success) {
      setSuccessMessage('Password reset successfully. Redirecting to login...')
      setTimeout(() => navigate('/login'), 2000)
      return
    }

    setError(result.error || 'Failed to reset password')
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <h1>Reset Password</h1>
          <p className="login-subtitle">
            {step === 1
              ? 'Enter your email to receive a verification code'
              : 'Enter the code sent to your email'}
          </p>
        </div>

        {successMessage ? (
          <div className="login-success">
            <p>{successMessage}</p>
          </div>
        ) : step === 1 ? (
          <form onSubmit={handleSendCode} className="login-form">
            {error && (
              <div className="login-error" role="alert">
                <p>{error}</p>
              </div>
            )}

            <div className="login-field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={submitting}
                autoFocus
                autoComplete="email"
              />
            </div>

            <button
              type="submit"
              className="login-submit"
              disabled={!email || submitting}
            >
              {submitting ? 'Sending code...' : 'Send reset code'}
            </button>

            <div className="login-links">
              <Link to="/login">Back to login</Link>
            </div>
          </form>
        ) : (
          <form onSubmit={handleResetPassword} className="login-form">
            {error && (
              <div className="login-error" role="alert">
                <p>{error}</p>
              </div>
            )}

            <div className="login-field">
              <label htmlFor="code">Verification Code</label>
              <input
                id="code"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Enter 6-digit code"
                disabled={submitting}
                autoFocus
                autoComplete="one-time-code"
              />
            </div>

            <div className="login-field">
              <label htmlFor="new-password">New Password</label>
              <input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                disabled={submitting}
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
              disabled={!code || !newPassword || !confirmPassword || submitting}
            >
              {submitting ? 'Resetting...' : 'Reset password'}
            </button>

            <div className="login-links">
              <Link to="/login">Back to login</Link>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
