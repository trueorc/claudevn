import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Radio, Sparkles, FolderGit2, ListTodo, Play, Target,
  Settings, Timer, Bell, LayoutDashboard,
  ChevronDown, Check
} from 'lucide-react'
import useSystemHealth from '../../hooks/useSystemHealth'
import useNotifications from '../../hooks/useNotifications'
import { useProjectContext } from '../../contexts/ProjectContext'
import './IconBar.css'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/directives', icon: Target, label: 'Directives' },
  { to: '/plan', icon: Play, label: 'Plan' },
  { to: '/backlog', icon: ListTodo, label: 'Backlog' },
  { to: '/marketplace', icon: Sparkles, label: 'Marketplace' },
  { to: '/network', icon: Radio, label: 'Network' },
  { to: '/projects', icon: FolderGit2, label: 'Projects' },
  { to: '/timing', icon: Timer, label: 'Timing' },
]

function CompactProjectSelector() {
  const { activeProject, projects, setActiveProject, loading } = useProjectContext()
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

  const handleSelect = (project) => {
    setActiveProject(project)
    setIsOpen(false)
  }

  const initial = activeProject ? activeProject.name.charAt(0).toUpperCase() : '?'
  const tooltipText = activeProject ? activeProject.name : 'Select project'

  return (
    <div className="iconbar-project-selector" ref={containerRef}>
      <button
        ref={triggerRef}
        className={`iconbar-project-trigger ${activeProject ? 'has-project' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        disabled={loading}
      >
        <span className="iconbar-project-initial">{initial}</span>
        <span className="iconbar-tooltip">{tooltipText}</span>
      </button>

      {isOpen && dropdownPos && (
        <div
          className="iconbar-project-dropdown"
          role="listbox"
          style={{
            bottom: `${dropdownPos.bottom}px`,
            left: `${dropdownPos.left}px`,
          }}
        >
          <div className="iconbar-project-dropdown-header">Projects</div>
          {projects.map((project) => (
            <button
              key={project.project_id}
              className={`iconbar-project-option ${activeProject?.project_id === project.project_id ? 'selected' : ''}`}
              onClick={() => handleSelect(project)}
              role="option"
              aria-selected={activeProject?.project_id === project.project_id}
            >
              <span className="iconbar-project-option-name">{project.name}</span>
              {activeProject?.project_id === project.project_id && <Check size={12} />}
            </button>
          ))}
          {projects.length === 0 && !loading && (
            <div className="iconbar-project-empty">No projects</div>
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
          {navItems.map(({ to, icon: Icon, label }) => (
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
          ))}
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

        <CompactProjectSelector />

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
