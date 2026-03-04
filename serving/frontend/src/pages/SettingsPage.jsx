import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Radio, User, Key } from 'lucide-react'
import useNetworkCapacity from '../hooks/useNetworkCapacity'
import { useUser } from '../hooks/useUser'
import { useCompute } from '../hooks/useCompute'
import { useAuth } from '../hooks/useAuth'
import SSHKeysPage from './SSHKeysPage'
import './SettingsPage.css'

const TABS = [
  { id: 'network', label: 'Network', icon: Radio },
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'ssh-keys', label: 'SSH Keys', icon: Key },
]

function NetworkSettings() {
  const { capacity, loading, error, updateCapacity } = useNetworkCapacity()
  const [maxInstances, setMaxInstances] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)

  useEffect(() => {
    if (capacity) {
      setMaxInstances(String(capacity.max_compute_instances))
    }
  }, [capacity])

  const handleSave = async () => {
    const value = parseInt(maxInstances, 10)
    if (isNaN(value) || value < 0) return
    setSaving(true)
    setSaveMsg(null)
    try {
      await updateCapacity(value)
      setSaveMsg('Saved')
      setTimeout(() => setSaveMsg(null), 2000)
    } catch {
      setSaveMsg('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="settings-loading">Loading...</div>
  if (error) return <div className="settings-error">Failed to load network settings: {error}</div>

  return (
    <div className="settings-section">
      <h2 className="settings-section-title">Network Capacity</h2>
      <div className="settings-card">
        <div className="settings-field">
          <label className="settings-label" htmlFor="max-compute">
            Max compute instances
          </label>
          <p className="settings-hint">
            Maximum number of compute instances that can register. Set to 0 for unlimited.
          </p>
          <div className="settings-input-row">
            <input
              id="max-compute"
              type="number"
              min="0"
              className="settings-input"
              value={maxInstances}
              onChange={(e) => setMaxInstances(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            <button
              className="settings-btn primary"
              onClick={handleSave}
              disabled={saving || maxInstances === String(capacity?.max_compute_instances)}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            {saveMsg && (
              <span className={`settings-save-msg ${saveMsg === 'Saved' ? 'success' : 'error'}`}>
                {saveMsg}
              </span>
            )}
          </div>
        </div>
        {capacity && (
          <div className="settings-info-row">
            <span className="settings-info-label">Current instances:</span>
            <span className="settings-info-value">{capacity.current_instances}</span>
            <span className="settings-info-label">Available slots:</span>
            <span className="settings-info-value">
              {capacity.available_slots === -1 ? 'Unlimited' : capacity.available_slots}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function ProfileSettings() {
  const { user, updateProfile } = useUser()
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
    return <div className="settings-loading">Not logged in</div>
  }

  return (
    <div className="settings-section">
      <h2 className="settings-section-title">User Info</h2>
      <div className="settings-card">
        {editing ? (
          <div className="settings-form">
            <label className="settings-form-label">
              Username
              <input
                className="settings-input"
                value={editUsername}
                onChange={e => setEditUsername(e.target.value)}
              />
            </label>
            <label className="settings-form-label">
              Email
              <input
                className="settings-input"
                value={editEmail}
                onChange={e => setEditEmail(e.target.value)}
                placeholder="Optional"
              />
            </label>
            {saveError && <p className="settings-error-text">{saveError}</p>}
            <div className="settings-form-actions">
              <button className="settings-btn primary" onClick={handleSave}>Save</button>
              <button className="settings-btn" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="settings-info">
            <div className="settings-field-row">
              <span className="settings-field-label">Username</span>
              <span className="settings-field-value">{user.username}</span>
            </div>
            <div className="settings-field-row">
              <span className="settings-field-label">Email</span>
              <span className="settings-field-value">{user.email || 'Not set'}</span>
            </div>
            <div className="settings-field-row">
              <span className="settings-field-label">Role</span>
              <span className={`settings-badge ${user.role}`}>{user.role}</span>
            </div>
            <div className="settings-field-row">
              <span className="settings-field-label">Member since</span>
              <span className="settings-field-value">
                {user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
              </span>
            </div>
            <button className="settings-btn" onClick={() => setEditing(true)}>Edit</button>
          </div>
        )}
      </div>

      <h2 className="settings-section-title">My Components</h2>
      <div className="settings-card">
        {computeLoading ? (
          <p className="settings-muted">Loading...</p>
        ) : ownedInstances.length === 0 ? (
          <p className="settings-muted">No components owned</p>
        ) : (
          <div className="settings-component-list">
            {ownedInstances.map(instance => (
              <div key={instance.instance_id} className="settings-component">
                <span className="settings-component-name">{instance.name}</span>
                <span className={`settings-badge ${instance.status}`}>{instance.status}</span>
                <span className={`settings-badge auth-${instance.auth_status || 'unauthorized'}`}>
                  {instance.auth_status || 'unauthorized'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <h2 className="settings-section-title">Auth Status</h2>
      <div className="settings-card">
        <div className="settings-field-row">
          <span className="settings-field-label">Claude auth</span>
          <span className={`settings-badge ${authStatus}`}>{authStatus || 'unknown'}</span>
        </div>
      </div>
    </div>
  )
}

function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'network'

  const setActiveTab = (tab) => {
    setSearchParams({ tab })
  }

  return (
    <div className="settings-page">
      <h1 className="settings-title">Settings</h1>

      <div className="settings-tabs">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`settings-tab ${activeTab === id ? 'active' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      <div className="settings-content">
        {activeTab === 'network' && <NetworkSettings />}
        {activeTab === 'profile' && <ProfileSettings />}
        {activeTab === 'ssh-keys' && <SSHKeysPage />}
      </div>
    </div>
  )
}

export default SettingsPage
