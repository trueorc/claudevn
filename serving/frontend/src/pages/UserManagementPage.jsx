import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, RotateCw, Mail, UserCheck, Clock } from 'lucide-react'
import { useToast } from '../hooks/useToast'
import { useCognitoAuth } from '../contexts/CognitoAuthContext'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { request } from '../api/index'
import './UserManagementPage.css'

function UserManagementPage() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showInviteForm, setShowInviteForm] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviting, setInviting] = useState(false)
  const [removingUser, setRemovingUser] = useState(null)
  const [removeLoading, setRemoveLoading] = useState(false)
  const [resendingUser, setResendingUser] = useState(null)
  const toast = useToast()
  const { isBypass } = useCognitoAuth()

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true)
      const data = await request('/cognito-users')
      setUsers(data.users || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isBypass) {
      fetchUsers()
    } else {
      setLoading(false)
    }
  }, [fetchUsers, isBypass])

  const handleInvite = async (e) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return

    setInviting(true)
    try {
      await request('/cognito-users/invite', {
        method: 'POST',
        body: JSON.stringify({ email: inviteEmail.trim() }),
      })
      toast.success(`Invitation sent to ${inviteEmail}`)
      setInviteEmail('')
      setShowInviteForm(false)
      fetchUsers()
    } catch (err) {
      toast.error(err.message || 'Failed to invite user')
    } finally {
      setInviting(false)
    }
  }

  const handleRemove = async () => {
    if (!removingUser) return
    setRemoveLoading(true)
    try {
      await request(`/cognito-users/${encodeURIComponent(removingUser)}`, {
        method: 'DELETE',
      })
      toast.success('User removed')
      setRemovingUser(null)
      fetchUsers()
    } catch (err) {
      toast.error(err.message || 'Failed to remove user')
    } finally {
      setRemoveLoading(false)
    }
  }

  const handleResend = async (username) => {
    setResendingUser(username)
    try {
      await request(`/cognito-users/${encodeURIComponent(username)}/resend-invite`, {
        method: 'POST',
      })
      toast.success('Invitation resent')
    } catch (err) {
      toast.error(err.message || 'Failed to resend invitation')
    } finally {
      setResendingUser(null)
    }
  }

  if (isBypass) {
    return (
      <div className="user-mgmt-page">
        <h1>User Management</h1>
        <div className="user-mgmt-empty">
          <p>User management is not available in bypass mode.</p>
          <p className="text-muted">Set AUTH_MODE=cognito and COGNITO_ADMIN_ENABLED=true to enable.</p>
        </div>
      </div>
    )
  }

  function statusBadge(status) {
    const map = {
      'CONFIRMED': { label: 'Active', className: 'badge-active' },
      'FORCE_CHANGE_PASSWORD': { label: 'Pending', className: 'badge-pending' },
      'COMPROMISED': { label: 'Compromised', className: 'badge-error' },
      'DISABLED': { label: 'Disabled', className: 'badge-disabled' },
    }
    const info = map[status] || { label: status, className: 'badge-default' }
    return <span className={`user-status-badge ${info.className}`}>{info.label}</span>
  }

  return (
    <div className="user-mgmt-page">
      <div className="user-mgmt-header">
        <h1>User Management</h1>
        <button
          className="btn-primary btn-sm"
          onClick={() => setShowInviteForm(!showInviteForm)}
        >
          <Plus size={14} /> Invite User
        </button>
      </div>

      {showInviteForm && (
        <form onSubmit={handleInvite} className="user-mgmt-invite-form">
          <input
            type="email"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder="user@example.com"
            disabled={inviting}
            autoFocus
          />
          <button type="submit" className="btn-primary btn-sm" disabled={!inviteEmail.trim() || inviting}>
            {inviting ? 'Sending...' : 'Send Invitation'}
          </button>
          <button type="button" className="btn-secondary btn-sm" onClick={() => setShowInviteForm(false)}>
            Cancel
          </button>
        </form>
      )}

      {error && (
        <div className="user-mgmt-error">
          <p>{error}</p>
          <button onClick={fetchUsers} className="btn-secondary btn-sm">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="user-mgmt-loading">Loading users...</div>
      ) : users.length === 0 ? (
        <div className="user-mgmt-empty">
          <p>No users found. Invite someone to get started.</p>
        </div>
      ) : (
        <div className="user-mgmt-table-container">
          <table className="user-mgmt-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.username}>
                  <td className="user-email">
                    <Mail size={14} />
                    {user.email}
                  </td>
                  <td>{statusBadge(user.status)}</td>
                  <td className="user-date">
                    {user.created
                      ? new Date(user.created).toLocaleDateString()
                      : '-'}
                  </td>
                  <td className="user-actions">
                    {user.status === 'FORCE_CHANGE_PASSWORD' && (
                      <button
                        className="btn-icon"
                        onClick={() => handleResend(user.username)}
                        disabled={resendingUser === user.username}
                        title="Resend invitation"
                      >
                        <RotateCw size={14} className={resendingUser === user.username ? 'spinning' : ''} />
                      </button>
                    )}
                    <button
                      className="btn-icon btn-icon-danger"
                      onClick={() => setRemovingUser(user.username)}
                      title="Remove user"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {removingUser && (
        <ConfirmDialog
          title="Remove User"
          message={`Are you sure you want to remove ${removingUser}? This cannot be undone.`}
          confirmLabel="Remove"
          confirmVariant="danger"
          loading={removeLoading}
          onConfirm={handleRemove}
          onCancel={() => setRemovingUser(null)}
        />
      )}
    </div>
  )
}

export default UserManagementPage
