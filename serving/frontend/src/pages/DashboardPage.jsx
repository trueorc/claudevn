import { useNavigate } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import { Plus, ArrowRight } from 'lucide-react'
import './DashboardPage.css'

function NoProjectDashboard({ onNewProject }) {
  const { projects, setActiveProject } = useProjectContext()
  const navigate = useNavigate()

  const handleSelectProject = (project) => {
    setActiveProject(project)
    navigate('/dashboard')
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-welcome">
        <img src="/ClaudeVN-Logo-64x64.png" alt="ClaudeVN" width="48" height="48" className="dashboard-welcome-logo" />
        <h1 className="dashboard-welcome-title">Welcome to ClaudeVN</h1>
        <p className="dashboard-welcome-subtitle">AI-powered development orchestration</p>
      </div>

      <div className="dashboard-entry-cards">
        <button className="dashboard-card dashboard-card-new" onClick={onNewProject}>
          <div className="dashboard-card-icon">
            <Plus size={28} strokeWidth={1.5} />
          </div>
          <div className="dashboard-card-content">
            <h2 className="dashboard-card-title">Start New Project</h2>
            <p className="dashboard-card-desc">
              Define goals, let the system decompose and orchestrate execution
            </p>
          </div>
          <div className="dashboard-card-action">
            <span>Get Started</span>
            <ArrowRight size={16} />
          </div>
        </button>

        <div className="dashboard-card dashboard-card-continue">
          <div className="dashboard-card-content">
            <h2 className="dashboard-card-title">Continue Working</h2>
            <p className="dashboard-card-desc">
              Pick up where you left off on an existing project
            </p>
          </div>

          {projects.length > 0 ? (
            <div className="dashboard-project-list">
              {projects.map((project) => (
                <button
                  key={project.project_id}
                  className="dashboard-project-item"
                  onClick={() => handleSelectProject(project)}
                >
                  <div className="dashboard-project-info">
                    <span
                      className="dashboard-project-dot"
                      style={{ background: project.color || 'var(--primary)' }}
                    />
                    <span className="dashboard-project-name">{project.name}</span>
                  </div>
                  <ArrowRight size={14} className="dashboard-project-arrow" />
                </button>
              ))}
            </div>
          ) : (
            <div className="dashboard-project-empty">
              No projects yet — start by creating one
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ActiveProjectDashboard() {
  const { activeProject } = useProjectContext()

  return (
    <div className="dashboard-page">
      <div className="dashboard-project-header">
        <h1 className="dashboard-project-title">{activeProject?.name}</h1>
        <p className="dashboard-project-desc">{activeProject?.description || 'No description'}</p>
      </div>

      <div className="dashboard-placeholder">
        <p className="dashboard-placeholder-text">
          Project dashboard coming soon — workflow lanes, attention items, and activity feed
        </p>
        <p className="dashboard-placeholder-hint">
          Use the navigation to access Directives, Plan, Backlog, and other areas
        </p>
      </div>
    </div>
  )
}

function DashboardPage() {
  const { activeProject } = useProjectContext()
  const navigate = useNavigate()

  const handleNewProject = () => {
    navigate('/projects')
  }

  if (activeProject) {
    return <ActiveProjectDashboard />
  }

  return <NoProjectDashboard onNewProject={handleNewProject} />
}

export default DashboardPage
