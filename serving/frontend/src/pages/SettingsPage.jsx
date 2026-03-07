import { useState } from 'react'
import { Settings, Save } from 'lucide-react'
import { useDisplayHostname } from '../hooks/useDisplayHostname'
import { useToast } from '../hooks/useToast'
import './SettingsPage.css'

function SettingsPage() {
  const { displayHostname, setDisplayHostname } = useDisplayHostname()
  const [hostname, setHostname] = useState(displayHostname)
  const toast = useToast()

  const handleSave = (e) => {
    e.preventDefault()
    setDisplayHostname(hostname)
    toast.success('Settings saved')
  }

  const isDirty = hostname !== displayHostname

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <form onSubmit={handleSave} className="settings-section">
        <h2 className="settings-section-title">Display</h2>

        <div className="settings-field">
          <label htmlFor="display-hostname" className="settings-label">
            Display Hostname
          </label>
          <p className="settings-description">
            Override the hostname shown in repository URLs. Leave empty to show the original server hostname.
          </p>
          <div className="settings-input-row">
            <input
              id="display-hostname"
              type="text"
              className="settings-input"
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              placeholder="e.g. localhost, demo.claudevn.com"
            />
            <button
              type="submit"
              className="settings-save-btn"
              disabled={!isDirty}
            >
              <Save size={14} />
              <span>Save</span>
            </button>
          </div>
          {displayHostname && (
            <p className="settings-hint">
              Current: repo URLs will display with hostname <code>{displayHostname}</code>
            </p>
          )}
        </div>
      </form>
    </div>
  )
}

export default SettingsPage
