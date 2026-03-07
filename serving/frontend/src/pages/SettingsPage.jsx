import { useState } from 'react'
import { Settings, Save, Check } from 'lucide-react'
import { useDisplayHostname } from '../hooks/useDisplayHostname'
import { useTheme } from '../contexts/ThemeContext'
import { useToast } from '../hooks/useToast'
import './SettingsPage.css'

const THEME_META = {
  dark: { label: 'Dark', description: 'Default dark theme', colors: ['#0f0f0f', '#1a1a1a', '#7c3aed', '#fafafa'] },
  light: { label: 'Light', description: 'Clean light theme', colors: ['#f8f8fa', '#ffffff', '#7c3aed', '#1a1a2e'] },
  retro: { label: 'Retro', description: 'Amber terminal vibes', colors: ['#1a1400', '#261e00', '#f59e0b', '#f5d97a'] },
  ocean: { label: 'Ocean', description: 'Deep blue seas', colors: ['#0a1628', '#0f1f36', '#06b6d4', '#e0f2fe'] },
  neon: { label: 'Neon', description: 'Cyberpunk glow', colors: ['#0a0a14', '#12121e', '#e040fb', '#f0e6ff'] },
}

function SettingsPage() {
  const { displayHostname, setDisplayHostname } = useDisplayHostname()
  const [hostname, setHostname] = useState(displayHostname)
  const { theme, setTheme, themes } = useTheme()
  const toast = useToast()

  const handleSave = (e) => {
    e.preventDefault()
    setDisplayHostname(hostname)
    toast.success('Settings saved')
  }

  const handleThemeChange = (newTheme) => {
    setTheme(newTheme)
    toast.success(`Theme changed to ${THEME_META[newTheme]?.label || newTheme}`)
  }

  const isDirty = hostname !== displayHostname

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-section">
        <h2 className="settings-section-title">Theme</h2>
        <p className="settings-description" style={{ marginBottom: 'var(--space-md)' }}>
          Choose your preferred color theme. This preference is saved per-user.
        </p>
        <div className="theme-grid">
          {themes.map((t) => {
            const meta = THEME_META[t]
            const isActive = theme === t
            return (
              <button
                key={t}
                className={`theme-card${isActive ? ' theme-card--active' : ''}`}
                onClick={() => handleThemeChange(t)}
              >
                <div className="theme-preview">
                  <div className="theme-preview-bg" style={{ background: meta.colors[0] }}>
                    <div className="theme-preview-sidebar" style={{ background: meta.colors[1] }} />
                    <div className="theme-preview-content">
                      <div className="theme-preview-accent" style={{ background: meta.colors[2] }} />
                      <div className="theme-preview-text" style={{ background: meta.colors[3], opacity: 0.6 }} />
                      <div className="theme-preview-text" style={{ background: meta.colors[3], opacity: 0.3, width: '60%' }} />
                    </div>
                  </div>
                </div>
                <div className="theme-info">
                  <span className="theme-name">{meta.label}</span>
                  <span className="theme-desc">{meta.description}</span>
                </div>
                {isActive && (
                  <div className="theme-active-badge">
                    <Check size={12} />
                  </div>
                )}
              </button>
            )
          })}
        </div>
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
