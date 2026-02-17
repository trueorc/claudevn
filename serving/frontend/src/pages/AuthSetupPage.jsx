/**
 * Full-page authentication setup component with guided wizard.
 *
 * Three-step onboarding flow:
 * 1. Welcome screen with platform introduction
 * 2. Token setup instructions with optional skip
 * 3. Success confirmation with auto-redirect
 */

import { useState, useCallback, useEffect } from 'react'
import './AuthSetupPage.css'

function AuthSetupPage({ status, message, submitToken, skipSetup }) {
  const [currentStep, setCurrentStep] = useState(1)
  const [token, setToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [validationError, setValidationError] = useState(null)
  const [successRedirectCountdown, setSuccessRedirectCountdown] = useState(null)

  const handleSubmit = useCallback(async () => {
    const trimmed = token.trim()
    if (!trimmed) return

    if (!trimmed.startsWith('sk-ant-oat01-')) {
      setValidationError('Token must start with "sk-ant-oat01-"')
      return
    }

    setValidationError(null)
    setSubmitting(true)
    try {
      await submitToken(trimmed)
      setToken('')
      setCurrentStep(3)
      setSuccessRedirectCountdown(3)
    } finally {
      setSubmitting(false)
    }
  }, [token, submitToken])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      handleSubmit()
    }
  }, [handleSubmit])

  const handleSkip = useCallback(() => {
    if (skipSetup) {
      skipSetup()
    }
  }, [skipSetup])

  const copyCommand = useCallback(() => {
    navigator.clipboard.writeText('claude setup-token')
  }, [])

  // Auto-redirect countdown on success
  useEffect(() => {
    if (successRedirectCountdown === null || successRedirectCountdown <= 0) return

    const timer = setTimeout(() => {
      if (successRedirectCountdown > 1) {
        setSuccessRedirectCountdown(successRedirectCountdown - 1)
      } else {
        // Redirect will happen naturally when auth status updates
        setSuccessRedirectCountdown(0)
      }
    }, 1000)

    return () => clearTimeout(timer)
  }, [successRedirectCountdown])

  return (
    <div className="auth-setup-page">
      <div className="auth-setup-card">
        <StepIndicator currentStep={currentStep} />

        {currentStep === 1 && (
          <WelcomeStep onNext={() => setCurrentStep(2)} />
        )}

        {currentStep === 2 && (
          <TokenSetupStep
            token={token}
            setToken={setToken}
            submitting={submitting}
            validationError={validationError}
            setValidationError={setValidationError}
            handleSubmit={handleSubmit}
            handleKeyDown={handleKeyDown}
            handleSkip={handleSkip}
            copyCommand={copyCommand}
            status={status}
            message={message}
          />
        )}

        {currentStep === 3 && (
          <SuccessStep countdown={successRedirectCountdown} />
        )}
      </div>
    </div>
  )
}

function StepIndicator({ currentStep }) {
  return (
    <div className="step-indicator">
      {[1, 2, 3].map((step) => (
        <div
          key={step}
          className={`step-dot ${step === currentStep ? 'active' : ''} ${step < currentStep ? 'completed' : ''}`}
        />
      ))}
    </div>
  )
}

function WelcomeStep({ onNext }) {
  return (
    <div className="wizard-step welcome-step">
      <div className="auth-setup-header">
        <h1>Welcome to ClaudeVN</h1>
        <p className="auth-setup-subtitle">AI Agent Orchestration Platform</p>
      </div>

      <div className="welcome-description">
        <p>
          ClaudeVN enables emergent, conversation-driven coordination between specialized AI agents.
          Define high-level goals, and watch as Claude Code instances collaborate to break down work,
          execute tasks, and deliver results.
        </p>
      </div>

      <button className="auth-setup-primary-btn" onClick={onNext}>
        Get Started
      </button>
    </div>
  )
}

function TokenSetupStep({
  token,
  setToken,
  submitting,
  validationError,
  setValidationError,
  handleSubmit,
  handleKeyDown,
  handleSkip,
  copyCommand,
  status,
  message,
}) {
  return (
    <div className="wizard-step token-step">
      <div className="auth-setup-header">
        <h1>Connect Your Account</h1>
        <p className="auth-setup-subtitle">Set up your Anthropic API credentials</p>
      </div>

      <div className="auth-setup-token-section">
        <p className="auth-setup-instructions">
          Run <code>claude setup-token</code> on any machine with a browser,
          then paste the resulting token below.
        </p>

        <button className="copy-command-btn" onClick={copyCommand}>
          Copy Command
        </button>

        <div className="auth-setup-code-container">
          <input
            type="password"
            className="auth-setup-code-input"
            value={token}
            onChange={(e) => {
              setToken(e.target.value)
              setValidationError(null)
            }}
            onKeyDown={handleKeyDown}
            placeholder="sk-ant-oat01-..."
            disabled={submitting}
            autoFocus
          />
          <button
            className="auth-setup-submit-btn"
            onClick={handleSubmit}
            disabled={!token.trim() || submitting}
          >
            {submitting ? 'Submitting...' : 'Submit'}
          </button>
        </div>

        {validationError && (
          <div className="auth-setup-error" role="alert">
            <p>{validationError}</p>
          </div>
        )}

        {status === 'error' && message && (
          <div className="auth-setup-error" role="alert">
            <p>{message}</p>
          </div>
        )}

        <button className="skip-link" onClick={handleSkip}>
          Skip for now
        </button>
      </div>
    </div>
  )
}

function SuccessStep({ countdown }) {
  return (
    <div className="wizard-step success-step">
      <div className="success-icon">
        <svg
          width="64"
          height="64"
          viewBox="0 0 64 64"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <circle cx="32" cy="32" r="32" fill="rgba(34, 197, 94, 0.15)" />
          <path
            d="M20 32L28 40L44 24"
            stroke="#22c55e"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <div className="auth-setup-header">
        <h1>Connected!</h1>
        <p className="auth-setup-subtitle">Your credentials are configured successfully</p>
      </div>

      {countdown !== null && countdown > 0 && (
        <p className="redirect-message">
          Redirecting to dashboard in {countdown}...
        </p>
      )}
    </div>
  )
}

export default AuthSetupPage
