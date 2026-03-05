import { useNavigate, NavLink } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import useIssues from '../hooks/useIssues'
import usePlanSummary from '../hooks/usePlanSummary'
import useRecentActivity from '../hooks/useRecentActivity'
import { Plus, ArrowRight, Target, Play, CheckCircle } from 'lucide-react'
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

function WorkflowLanes({ stats, planData }) {
  const defineCount = stats ? (stats.by_status?.pending || 0) + (stats.by_status?.new || 0) : 0
  const executeActive = planData?.active_count || 0
  const executeQueued = planData?.queued_count || 0
  const reviewCount = stats ? (stats.by_status?.in_review || 0) + (stats.by_status?.testing || 0) : 0
  const doneCount = stats?.by_status?.done || 0

  const lanes = [
    {
      key: 'define',
      icon: Target,
      title: 'Define',
      desc: 'Describe what you want built',
      to: '/directives',
      active: defineCount > 0,
      content: defineCount > 0
        ? `${defineCount} item${defineCount !== 1 ? 's' : ''} pending`
        : 'No pending items',
    },
    {
      key: 'execute',
      icon: Play,
      title: 'Execute',
      desc: 'System builds your backlog',
      to: '/plan',
      active: executeActive > 0,
      content: executeActive > 0
        ? `${executeActive} active${executeQueued > 0 ? `, ${executeQueued} queued` : ''}`
        : executeQueued > 0
          ? `${executeQueued} queued`
          : 'No active work',
    },
    {
      key: 'review',
      icon: CheckCircle,
      title: 'Review',
      desc: 'Review and merge results',
      to: '/backlog',
      active: reviewCount > 0,
      content: reviewCount > 0
        ? `${reviewCount} awaiting review`
        : doneCount > 0
          ? `${doneCount} completed`
          : 'Nothing to review',
    },
  ]

  return (
    <div className="dashboard-lanes">
      {lanes.map(({ key, icon: Icon, title, desc, to, active, content }) => (
        <NavLink key={key} to={to} className={`dashboard-lane ${active ? 'has-activity' : ''}`}>
          <div className="dashboard-lane-header">
            <Icon size={16} strokeWidth={1.5} />
            <span className="dashboard-lane-title">{title}</span>
          </div>
          <p className="dashboard-lane-desc">{desc}</p>
          <p className="dashboard-lane-status">{content}</p>
          <div className="dashboard-lane-link">
            <span>Open</span>
            <ArrowRight size={12} />
          </div>
        </NavLink>
      ))}
    </div>
  )
}

function AttentionSection({ items, stats }) {
  const attentionItems = []

  // Blocked items
  const blockedCount = stats?.by_status?.blocked || 0
  if (blockedCount > 0) {
    attentionItems.push({
      key: 'blocked',
      text: `${blockedCount} item${blockedCount !== 1 ? 's' : ''} blocked — may need dependency resolution`,
      to: '/backlog',
    })
  }

  // Uncharacterized items
  const uncharacterized = items.filter(i => i.characterization_status === 'pending').length
  if (uncharacterized > 0) {
    attentionItems.push({
      key: 'uncharacterized',
      text: `${uncharacterized} item${uncharacterized !== 1 ? 's' : ''} awaiting characterization`,
      to: '/backlog',
    })
  }

  // Items ready for review
  const reviewCount = (stats?.by_status?.in_review || 0) + (stats?.by_status?.testing || 0)
  if (reviewCount > 0) {
    attentionItems.push({
      key: 'review',
      text: `${reviewCount} item${reviewCount !== 1 ? 's' : ''} ready for review`,
      to: '/backlog',
    })
  }

  if (attentionItems.length === 0) return null

  return (
    <div className="dashboard-attention">
      <h3 className="dashboard-section-title">Your attention is needed</h3>
      <div className="dashboard-attention-list">
        {attentionItems.slice(0, 5).map(({ key, text, to }) => (
          <NavLink key={key} to={to} className="dashboard-attention-item">
            <span className="dashboard-attention-text">{text}</span>
            <ArrowRight size={12} className="dashboard-attention-arrow" />
          </NavLink>
        ))}
      </div>
    </div>
  )
}

function ActivityFeed({ items }) {
  const { events } = useRecentActivity({ items, maxEvents: 10 })

  if (events.length === 0) return null

  return (
    <div className="dashboard-activity">
      <h3 className="dashboard-section-title">Recent Activity</h3>
      <div className="dashboard-activity-list">
        {events.map((event) => (
          <div key={`${event.id}-${event.timestamp}`} className="dashboard-activity-item">
            <span className="dashboard-activity-desc">{event.description}</span>
            <span className="dashboard-activity-time">{event.relativeTime}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ActiveProjectDashboard() {
  const { activeProject } = useProjectContext()
  const { items, stats, loading: issuesLoading } = useIssues({
    pollInterval: 15000,
    filters: { project_id: activeProject?.project_id },
  })
  const { data: planData, loading: planLoading } = usePlanSummary(activeProject?.project_id, {
    pollInterval: 15000,
  })

  return (
    <div className="dashboard-page">
      <div className="dashboard-project-header">
        <h1 className="dashboard-project-title">{activeProject?.name}</h1>
        {activeProject?.description && (
          <p className="dashboard-project-desc">{activeProject.description}</p>
        )}
      </div>

      <div className="dashboard-active-content">
        <WorkflowLanes stats={stats} planData={planData} />
        <AttentionSection items={items} stats={stats} />
        <ActivityFeed items={items} />
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
