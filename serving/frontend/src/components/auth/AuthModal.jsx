import { useState, useEffect, useCallback } from 'react'
import { Shield, ShieldCheck, ShieldX, Copy, Check } from 'lucide-react'
import Modal from '../common/Modal'
import { submitToken, getTokenInfo, revokeToken } from '../../api/auth'
import './AuthModal.css'

const TOKEN_PREFIX = 'sk-ant-oat01-'

function AuthModal({ isOpen, onClose, componentId, componentName, componentType = 'compute', onAuthChange }) {
  const [step, setStep] = useState('loading') // loading, instructions, success, error, authorized
  const [token, setToken] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [tokenInfo, setTokenInfo] = useState(null)
  const [copied, setCopied] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)

  const isValidFormat = token.startsWith(TOKEN_PREFIX) && token.length > TOKEN_PREFIX.length

  const loadTokenInfo = useCallback(async () => {
    if (!componentId) return
    try {
      const info = await getTokenInfo(componentId)
      if (info && info.status === 'active') {
        setTokenInfo(info)
        setStep('authorized')
      } else {
        setStep('instructions')
      }
    } catch {
      setStep('instructions')
    }
  }, [componentId])

  useEffect(() => {
    if (isOpen) {
      setToken('')
      setError(null)
      setSubmitting(false)
      setCopied(false)
      setConfirmRevoke(false)
      setRevoking(false)
      setStep('loading')
      loadTokenInfo()
    }
  }, [isOpen, loadTokenInfo])

  const handleSubmit = async () => {
    if (!isValidFormat || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await submitToken(token, componentId, componentType)
      setStep('success')
      if (onAuthChange) onAuthChange()
      setTimeout(() => {
        onClose()
      }, 3000)
    } catch (err) {
      setError(err.message)
      setStep('error')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevoke = async () => {
    if (revoking) return
    setRevoking(true)
    try {
      await revokeToken(componentId)
      setTokenInfo(null)
      setConfirmRevoke(false)
      setStep('instructions')
      if (onAuthChange) onAuthChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setRevoking(false)
    }
  }

  const handleCopyCommand = () => {
    navigator.clipboard.writeText('claude setup-token')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && isValidFormat && !submitting) {
      handleSubmit()
    }
  }

  const displayName = componentName || componentId

  const formatDate = (iso) => {
    if (!iso) return '-'
    try {
      return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return iso
    }
  }

  const title = step === 'authorized'
    ? `${displayName} - Authorized`
    : `Authorize ${displayName}`

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} width="480px">
      <div className="auth-modal">
        {step === 'loading' && (
          <div className="auth-loading">Loading...</div>
        )}

        {step === 'authorized' && tokenInfo && (
          <div className="auth-authorized">
            <div className="auth-status-banner auth-status-active">
              <ShieldCheck size={20} />
              <div>
                <div className="auth-status-text">Authorized</div>
                <div className="auth-status-detail">
                  Expires {formatDate(tokenInfo.expires_at)}
                </div>
              </div>
            </div>

            {!confirmRevoke ? (
              <div className="auth-actions">
                <button className="btn-secondary" onClick={() => {
                  setStep('instructions')
                  setTokenInfo(null)
                }}>
                  Submit New Token
                </button>
                <button className="btn-danger-sm" onClick={() => setConfirmRevoke(true)}>
                  Revoke
                </button>
              </div>
            ) : (
              <div className="auth-confirm-revoke">
                <p>Are you sure you want to revoke authorization for {displayName}?</p>
                <div className="auth-actions">
                  <button className="btn-secondary" onClick={() => setConfirmRevoke(false)} disabled={revoking}>
                    Cancel
                  </button>
                  <button className="btn-danger-sm" onClick={handleRevoke} disabled={revoking}>
                    {revoking ? 'Revoking...' : 'Confirm Revoke'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {step === 'instructions' && (
          <>
            <div className="auth-instructions">
              <p>To authorize this component, generate a token from any machine with Claude Code installed:</p>
              <ol>
                <li>Open a terminal on any machine with Claude Code</li>
                <li>
                  Run:{' '}
                  <code className="auth-command" onClick={handleCopyCommand}>
                    claude setup-token
                    <span className="copy-icon">
                      {copied ? <Check size={12} /> : <Copy size={12} />}
                    </span>
                  </code>
                </li>
                <li>Complete the login in your browser</li>
                <li>Copy the token that appears</li>
                <li>Paste it below</li>
              </ol>
            </div>

            <div className="auth-input-group">
              <label htmlFor="auth-token-input" className="auth-input-label">Token</label>
              <input
                id="auth-token-input"
                type="password"
                className="auth-token-input"
                placeholder={TOKEN_PREFIX + '...'}
                value={token}
                onChange={(e) => { setToken(e.target.value); setError(null) }}
                onKeyDown={handleKeyDown}
                autoFocus
                autoComplete="off"
              />
              {token && !isValidFormat && (
                <div className="auth-format-hint">Token must start with {TOKEN_PREFIX}</div>
              )}
            </div>

            {error && (
              <div className="auth-error">{error}</div>
            )}

            <div className="auth-actions">
              <button className="btn-secondary" onClick={onClose}>Cancel</button>
              <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={!isValidFormat || submitting}
              >
                {submitting ? 'Authorizing...' : 'Authorize'}
              </button>
            </div>
          </>
        )}

        {step === 'success' && (
          <div className="auth-success">
            <div className="auth-status-banner auth-status-active">
              <ShieldCheck size={24} />
              <div>
                <div className="auth-status-text">Component authorized!</div>
                <div className="auth-status-detail">This dialog will close automatically.</div>
              </div>
            </div>
          </div>
        )}

        {step === 'error' && (
          <div className="auth-error-state">
            <div className="auth-status-banner auth-status-error">
              <ShieldX size={24} />
              <div>
                <div className="auth-status-text">Authorization failed</div>
                <div className="auth-status-detail">{error}</div>
              </div>
            </div>
            <div className="auth-actions">
              <button className="btn-secondary" onClick={() => { setStep('instructions'); setError(null) }}>
                Try Again
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

export default AuthModal
