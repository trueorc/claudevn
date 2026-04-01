import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Radio, Sparkles, FolderGit2, ListTodo, Play, ShieldCheck, GitBranch,
  Settings, Timer, Bell, LayoutDashboard,
  LogOut
} from 'lucide-react'
import useSystemHealth from '../../hooks/useSystemHealth'
import useNotifications from '../../hooks/useNotifications'
import { useProjectContext } from '../../contexts/ProjectContext'
import { useAuth } from '../../contexts/auth/AuthContext'
import './IconBar.css'

const navItems = [
  // Core
  { to: '/dashboard', icon: LayoutDashboard, label: 'Control Center' },
  // Process: Plan → Execute → Verify
  { to: '/plan', icon: GitBranch, label: 'Plan', projectRequired: true },
  { to: '/execute', icon: Play, label: 'Execute', projectRequired: true },
  { to: '/verify', icon: ShieldCheck, label: 'Verify', projectRequired: true },
  // Administrative
  { to: '/work', icon: ListTodo, label: 'Work Units', projectRequired: true },
  { to: '/projects', icon: FolderGit2, label: 'Projects' },
  { to: '/network', icon: Radio, label: 'Network' },
  { to: '/marketplace', icon: Sparkles, label: 'Marketplace' },
  { to: '/timing', icon: Timer, label: 'Timing', projectRequired: true },
]

function ProfileAvatar() {
  const { user, logout, isBypass } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [dropdownPos, setDropdownPos] = useState(null)
  const containerRef = useRef(null)
  const triggerRef = useRef(null)

  useEffect(() => {
    if (isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setDropdownPos({
        bottom: window.innerHeight - rect.top + 4,
        left: rect.right + 8,
      })
    }
  }, [isOpen])

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') setIsOpen(false)
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const displayName = user?.username || user?.email || '?'
  const initial = displayName.charAt(0).toUpperCase()

  const handleLogout = async () => {
    setIsOpen(false)
    await logout()
    window.location.href = '/login'
  }

  return (
    <div className="iconbar-profile" ref={containerRef}>
      <button
        ref={triggerRef}
        className="iconbar-profile-trigger"
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <span className="iconbar-profile-initial">{initial}</span>
        <span className="iconbar-tooltip">{displayName}</span>
      </button>

      {isOpen && dropdownPos && (
        <div
          className="iconbar-profile-dropdown"
          role="menu"
          style={{
            bottom: `${dropdownPos.bottom}px`,
            left: `${dropdownPos.left}px`,
          }}
        >
          <div className="iconbar-profile-dropdown-header">
            {displayName}
          </div>
          {!isBypass && (
            <button
              className="iconbar-profile-option"
              onClick={handleLogout}
              role="menuitem"
            >
              <LogOut size={14} />
              <span>Log out</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function IconBar() {
  const { health, overallStatus, loading } = useSystemHealth({ pollInterval: 60000 })
  const { activeProject } = useProjectContext()
  const { unreadCount } = useNotifications(activeProject?.project_id, { pollInterval: 15000 })

  const getHealthClass = () => {
    if (loading) return 'connecting'
    switch (overallStatus) {
      case 'healthy': return 'connected'
      case 'degraded': return 'degraded'
      case 'unhealthy':
      case 'offline': return 'offline'
      default: return 'connecting'
    }
  }

  const getHealthTitle = () => {
    if (loading) return 'Checking health...'
    switch (overallStatus) {
      case 'healthy': return 'All systems healthy'
      case 'degraded': return 'Some services degraded'
      case 'unhealthy':
      case 'offline': return 'Services offline'
      default: return 'Unknown status'
    }
  }

  return (
    <nav className="iconbar">
      <div className="iconbar-top">
        <div className="iconbar-brand">
          <img src="/ClaudeVN-Logo-64x64.png" alt="ClaudeVN" width="24" height="24" />
          {health?.version && (
            <span className="iconbar-version">v{health.version}</span>
          )}
        </div>

        <div className="iconbar-divider" />

        <div className="iconbar-nav">
          {navItems.map(({ to, icon: Icon, label, projectRequired }) => {
            const isDisabled = projectRequired && !activeProject
            if (isDisabled) {
              return (
                <span
                  key={to}
                  className="iconbar-item iconbar-item-disabled"
                  title={`${label} — select a project first`}
                >
                  <Icon size={20} strokeWidth={1.5} />
                  <span className="iconbar-tooltip">{label} — select a project first</span>
                </span>
              )
            }
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `iconbar-item ${isActive ? 'active' : ''}`
                }
              >
                <Icon size={20} strokeWidth={1.5} />
                <span className="iconbar-tooltip">{label}</span>
              </NavLink>
            )
          })}
        </div>
      </div>

      <div className="iconbar-bottom">
        <NavLink
          to="/notifications"
          className={({ isActive }) =>
            `iconbar-item ${isActive ? 'active' : ''}`
          }
        >
          <div className="iconbar-notification-wrap">
            <Bell size={20} strokeWidth={1.5} />
            {unreadCount > 0 && (
              <span className="iconbar-notification-badge">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </div>
          <span className="iconbar-tooltip">Notifications</span>
        </NavLink>

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `iconbar-item ${isActive ? 'active' : ''}`
          }
        >
          <Settings size={20} strokeWidth={1.5} />
          <span className="iconbar-tooltip">Settings</span>
        </NavLink>

        <div className="iconbar-divider" />

        <ProfileAvatar />

        <NavLink
          to="/network"
          className="iconbar-health"
          title={getHealthTitle()}
        >
          <div className={`iconbar-health-dot ${getHealthClass()}`} />
        </NavLink>
      </div>
    </nav>
  )
}

export default IconBar
