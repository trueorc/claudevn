import { useState, useEffect, useRef } from 'react'
import { Hammer, Shield, FlaskConical, TrendingUp, ChevronDown } from 'lucide-react'
import { listPresets, activatePreset } from '../../api/profilePresets'
import './ProfileSwitcher.css'

const ICON_MAP = {
  Hammer,
  Shield,
  FlaskConical,
  TrendingUp,
}

function ProfileSwitcher({ projectId, activePreset, activePresetLabel, activePresetColor, onPresetChange }) {
  const [presets, setPresets] = useState([])
  const [open, setOpen] = useState(false)
  const [activating, setActivating] = useState(null)
  const dropdownRef = useRef(null)

  useEffect(() => {
    listPresets().then(setPresets).catch(() => {})
  }, [])

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleActivate = async (presetName) => {
    if (activating || presetName === activePreset) {
      setOpen(false)
      return
    }
    setActivating(presetName)
    try {
      await activatePreset(presetName, projectId)
      if (onPresetChange) onPresetChange()
    } catch (err) {
      console.error('Failed to activate preset:', err)
    } finally {
      setActivating(null)
      setOpen(false)
    }
  }

  const currentLabel = activePresetLabel || 'No Profile'
  const currentColor = activePresetColor || 'var(--text-muted)'
  const CurrentIcon = activePreset ? ICON_MAP[presets.find(p => p.name === activePreset)?.icon] : null

  return (
    <div className="profile-switcher" ref={dropdownRef}>
      <button
        className="profile-switcher-trigger"
        onClick={() => setOpen(!open)}
        style={{ '--preset-color': currentColor }}
      >
        {CurrentIcon && <CurrentIcon size={14} />}
        <span className="profile-switcher-label">{currentLabel}</span>
        <ChevronDown size={12} className={`profile-switcher-chevron ${open ? 'profile-switcher-chevron--open' : ''}`} />
      </button>

      {open && (
        <div className="profile-switcher-dropdown">
          <div className="profile-switcher-dropdown-header">Work Profile</div>
          {presets.map((preset) => {
            const Icon = ICON_MAP[preset.icon]
            const isActive = preset.name === activePreset
            const isLoading = activating === preset.name
            return (
              <button
                key={preset.name}
                className={`profile-switcher-option ${isActive ? 'profile-switcher-option--active' : ''}`}
                onClick={() => handleActivate(preset.name)}
                disabled={isLoading}
                style={{ '--preset-color': preset.color }}
              >
                <div className="profile-switcher-option-icon">
                  {Icon && <Icon size={16} />}
                </div>
                <div className="profile-switcher-option-content">
                  <span className="profile-switcher-option-label">{preset.label}</span>
                  <span className="profile-switcher-option-desc">{preset.description}</span>
                </div>
                {isActive && <span className="profile-switcher-option-badge">Active</span>}
                {isLoading && <span className="profile-switcher-option-badge">...</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default ProfileSwitcher
