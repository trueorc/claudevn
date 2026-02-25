import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { Radio, Sparkles, FolderGit2, ListTodo, Play, Target, ChevronDown, Check, Key, Settings } from 'lucide-react'
import useSystemHealth from '../../hooks/useSystemHealth'
import { useProjectContext } from '../../contexts/ProjectContext'
import NotificationBell from '../notifications/NotificationBell'
import './Sidebar.css'

const navItems = [
  { to: '/network', icon: Radio, label: 'Network' },
  { to: '/projects', icon: FolderGit2, label: 'Projects' },
  { to: '/marketplace', icon: Sparkles, label: 'Marketplace' },
  { to: '/directives', icon: Target, label: 'Directives' },
  { to: '/plan', icon: Play, label: 'Plan' },
  { to: '/backlog', icon: ListTodo, label: 'Backlog' },
  { to: '/settings/ssh-keys', icon: Key, label: 'SSH Keys' },
]

function ProjectSelector() {
  const { activeProject, projects, setActiveProject, loading } = useProjectContext()
  const [isOpen, setIsOpen] = useState(false)
  const [dropdownPos, setDropdownPos] = useState(null)
  const containerRef = useRef(null)
  const triggerRef = useRef(null)

  // Position dropdown above trigger using fixed positioning to escape overflow clipping
  useEffect(() => {
    if (isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setDropdownPos({
        bottom: window.innerHeight - rect.top + 4,
        left: rect.left,
        maxHeight: rect.top - 8,
      })
    }
  }, [isOpen])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close dropdown on escape key
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
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

  const displayName = activeProject ? activeProject.name : 'No Project'

  return (
    <div className="project-selector" ref={containerRef}>
      <button
        ref={triggerRef}
        className={`project-selector-trigger ${activeProject ? 'has-project' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title={activeProject ? `Active project: ${activeProject.name}` : 'No project selected'}
        disabled={loading}
      >
        <span className="project-selector-name">{displayName}</span>
        <ChevronDown size={12} className={`project-selector-chevron ${isOpen ? 'open' : ''}`} />
      </button>

      {isOpen && dropdownPos && (
        <div
          className="project-selector-dropdown"
          role="listbox"
          style={{
            bottom: `${dropdownPos.bottom}px`,
            left: `${dropdownPos.left}px`,
            maxHeight: `${dropdownPos.maxHeight}px`,
          }}
        >
          {projects.map((project) => (
            <button
              key={project.project_id}
              className={`project-selector-option ${activeProject?.project_id === project.project_id ? 'selected' : ''}`}
              onClick={() => handleSelect(project)}
              role="option"
              aria-selected={activeProject?.project_id === project.project_id}
            >
              <span className="project-option-name">{project.name}</span>
              {activeProject?.project_id === project.project_id && <Check size={12} className="project-option-check" />}
            </button>
          ))}

          {projects.length === 0 && !loading && (
            <div className="project-selector-empty">No projects</div>
          )}
        </div>
      )}
    </div>
  )
}

function Sidebar() {
  const { overallStatus, loading } = useSystemHealth({ pollInterval: 60000 })
  const { activeProject } = useProjectContext()

  const getIndicatorClass = () => {
    if (loading) return 'connecting'
    switch (overallStatus) {
      case 'healthy':
        return 'connected'
      case 'degraded':
        return 'degraded'
      case 'unhealthy':
      case 'offline':
        return 'offline'
      default:
        return 'connecting'
    }
  }

  const getIndicatorTitle = () => {
    if (loading) return 'Checking health...'
    switch (overallStatus) {
      case 'healthy':
        return 'All systems healthy'
      case 'degraded':
        return 'Some services degraded'
      case 'unhealthy':
      case 'offline':
        return 'Services offline'
      default:
        return 'Unknown status'
    }
  }

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <img src="/ClaudeVN-Logo-64x64.png" alt="ClaudeVN" width="28" height="28" />
        <span className="sidebar-brand-text">ClaudeVN</span>
      </div>

      <div className="sidebar-divider" />

      <div className="sidebar-nav">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
            title={label}
          >
            <Icon size={18} strokeWidth={1.5} />
            <span className="nav-item-label">{label}</span>
          </NavLink>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-footer-row">
          <ProjectSelector />
          <NotificationBell projectId={activeProject?.project_id} />
        </div>
        <NavLink to="/network" className="sidebar-health" title={getIndicatorTitle()}>
          <div className={`connection-indicator ${getIndicatorClass()}`} />
          <span className="connection-label">{getIndicatorTitle()}</span>
        </NavLink>
      </div>
    </nav>
  )
}

export default Sidebar
