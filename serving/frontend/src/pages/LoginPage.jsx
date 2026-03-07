import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/auth/AuthContext'
import './LoginPage.css'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  const { login, isLocal } = useAuth()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!email || !password) return

    setSubmitting(true)
    setError(null)

    const result = await login(email, password)
    setSubmitting(false)

    if (result.challenge === 'NEW_PASSWORD_REQUIRED') {
      navigate('/set-password')
      return
    }

    if (result.success) {
      navigate('/')
      return
    }

    setError(result.error || 'Login failed')
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <h1>ClaudeVN</h1>
          <p className="login-subtitle">Sign in to your network</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="login-error" role="alert">
              <p>{error}</p>
            </div>
          )}

          <div className="login-field">
            <label htmlFor="email">{isLocal ? 'Username' : 'Email'}</label>
            <input
              id="email"
              type={isLocal ? 'text' : 'email'}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={isLocal ? 'Enter username' : 'you@example.com'}
              disabled={submitting}
              autoFocus
              autoComplete={isLocal ? 'username' : 'email'}
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={submitting}
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className="login-submit"
            disabled={!email || !password || submitting}
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>

          {!isLocal && (
            <div className="login-links">
              <Link to="/forgot-password">Forgot password?</Link>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
