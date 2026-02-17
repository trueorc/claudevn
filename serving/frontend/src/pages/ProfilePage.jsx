import { useState, useEffect, useCallback } from 'react'
import { useUser } from '../hooks/useUser'
import { useCompute } from '../hooks/useCompute'
import { useAuth } from '../hooks/useAuth'
import './ProfilePage.css'

function ProfilePage() {
  const { user, isOwner, updateProfile, error: userError } = useUser()
  const { instances, loading: computeLoading } = useCompute()
  const { status: authStatus } = useAuth()

  const [editUsername, setEditUsername] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editing, setEditing] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    if (user) {
      setEditUsername(user.username || '')
      setEditEmail(user.email || '')
    }
  }, [user])

  const ownedInstances = instances?.filter(i => i.owner_id === user?.user_id) || []
  const totalUsers = 0 // TODO: fetch from admin endpoint when available

  const handleSave = async () => {
    setSaveError(null)
    try {
      await updateProfile({
        username: editUsername !== user.username ? editUsername : undefined,
        email: editEmail !== (user.email || '') ? editEmail : undefined,
      })
      setEditing(false)
    } catch (err) {
      setSaveError(err.message)
    }
  }

  if (!user) {
    return (
      <div className="profile-page">
        <div className="profile-card">
          <p className="profile-empty">Not logged in</p>
        </div>
      </div>
    )
  }

  return (
    <div className="profile-page">
      <h1 className="profile-title">Profile</h1>

      {/* User Info */}
      <div className="profile-card">
        <h2>User Info</h2>
        {editing ? (
          <div className="profile-form">
            <label>
              Username
              <input
                value={editUsername}
                onChange={e => setEditUsername(e.target.value)}
              />
            </label>
            <label>
              Email
              <input
                value={editEmail}
                onChange={e => setEditEmail(e.target.value)}
                placeholder="Optional"
              />
            </label>
            {saveError && <p className="profile-error">{saveError}</p>}
            <div className="profile-actions">
              <button className="profile-btn primary" onClick={handleSave}>Save</button>
              <button className="profile-btn" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="profile-info">
            <div className="profile-field">
              <span className="profile-label">Username</span>
              <span className="profile-value">{user.username}</span>
            </div>
            <div className="profile-field">
              <span className="profile-label">Email</span>
              <span className="profile-value">{user.email || 'Not set'}</span>
            </div>
            <div className="profile-field">
              <span className="profile-label">Role</span>
              <span className={`profile-badge ${user.role}`}>{user.role}</span>
            </div>
            <div className="profile-field">
              <span className="profile-label">Member since</span>
              <span className="profile-value">
                {user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
              </span>
            </div>
            <button className="profile-btn" onClick={() => setEditing(true)}>Edit</button>
          </div>
        )}
      </div>

      {/* My Components */}
      <div className="profile-card">
        <h2>My Components</h2>
        {computeLoading ? (
          <p className="profile-empty">Loading...</p>
        ) : ownedInstances.length === 0 ? (
          <p className="profile-empty">No components owned</p>
        ) : (
          <div className="profile-component-list">
            {ownedInstances.map(instance => (
              <div key={instance.instance_id} className="profile-component">
                <div className="profile-component-info">
                  <span className="profile-component-name">{instance.name}</span>
                  <span className={`profile-badge ${instance.status}`}>{instance.status}</span>
                  <span className={`profile-badge auth-${instance.auth_status || 'unauthorized'}`}>
                    {instance.auth_status || 'unauthorized'}
                  </span>
                </div>
                {instance.auth_expires_at && (
                  <span className="profile-component-expiry">
                    Expires: {new Date(instance.auth_expires_at).toLocaleDateString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Network Info (owner only) */}
      {isOwner && (
        <div className="profile-card">
          <h2>Network Info</h2>
          <div className="profile-info">
            <div className="profile-field">
              <span className="profile-label">Total components</span>
              <span className="profile-value">{instances?.length || 0}</span>
            </div>
            <div className="profile-field">
              <span className="profile-label">Unauthorized components</span>
              <span className="profile-value">
                {instances?.filter(i => !i.auth_status || i.auth_status === 'unauthorized').length || 0}
              </span>
            </div>
            <div className="profile-field">
              <span className="profile-label">Claude auth</span>
              <span className={`profile-badge ${authStatus}`}>{authStatus || 'unknown'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProfilePage
