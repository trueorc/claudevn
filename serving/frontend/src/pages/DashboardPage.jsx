import { useState, useCallback } from 'react'
import { useNavigate, NavLink } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import useIssues from '../hooks/useIssues'
import usePlanSummary from '../hooks/usePlanSummary'
import useRecentActivity from '../hooks/useRecentActivity'
import { createProject } from '../api/projects'
import { createGoal } from '../api/workmap'
import { Plus, ArrowRight, Target, Play, CheckCircle, X } from 'lucide-react'
import './DashboardPage.css'

const GUIDED_STEPS = [
  { number: 1, label: 'Create project' },
  { number: 2, label: 'First directive' },
  { number: 3, label: 'Done' },
]

function StepIndicator({ currentStep }) {
  return (
    <div className="guided-steps">
      {GUIDED_STEPS.map((step, idx) => {
        const done = currentStep > step.number
        const active = currentStep === step.number
        return (
          <div key={step.number} className="guided-step-item">
            <div className={`guided-step-dot ${active ? 'active' : ''} ${done ? 'done' : ''}`}>
              {done ? <CheckCircle size={12} /> : <span>{step.number}</span>}
            </div>
            <span className={`guided-step-label ${active ? 'active' : ''}`}>{step.label}</span>
            {idx < GUIDED_STEPS.length - 1 && <div className="guided-step-connector" />}
          </div>
        )
      })}
    </div>
  )
}

function GuidedSetup({ onExit }) {
  const [step, setStep] = useState(1)
  const [projectName, setProjectName] = useState('')
  const [projectDescription, setProjectDescription] = useState('')
  const [directive, setDirective] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [createdProject, setCreatedProject] = useState(null)
  const { setActiveProject, refreshProjects } = useProjectContext()
  const navigate = useNavigate()

  const handleCreateProject = useCallback(async (e) => {
    e.preventDefault()
    if (!projectName.trim()) {
      setError('Project name is required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const project = await createProject({
        name: projectName.trim(),
        description: projectDescription.trim() || '',
        repos: [],
      })
      setCreatedProject(project)
      setActiveProject(project)
      await refreshProjects()
      setStep(2)
    } catch (err) {
      setError(err.message || 'Failed to create project')
    } finally {
      setSaving(false)
    }
  }, [projectName, projectDescription, setActiveProject, refreshProjects])

  const handleSubmitDirective = useCallback(async (e) => {
    e.preventDefault()
    if (!directive.trim()) {
      setError('Please describe what you want to build')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createGoal({
        title: directive.trim().slice(0, 500),
        description: directive.trim(),
        priority: 'P2',
        project_id: createdProject.project_id,
      })
      setStep(3)
    } catch (err) {
      setError(err.message || 'Failed to submit directive')
    } finally {
      setSaving(false)
    }
  }, [directive, createdProject])

  const handleSkipDirective = useCallback(() => {
    setStep(3)
  }, [])

  const handleFinish = useCallback(() => {
    navigate('/dashboard')
  }, [navigate])

  return (
    <div className="guided-setup">
      <div className="guided-setup-header">
        <StepIndicator currentStep={step} />
        <button className="guided-exit-btn" onClick={onExit} title="Exit setup">
          <X size={16} />
        </button>
      </div>

      <div className="guided-setup-body">
        {step === 1 && (
          <form className="guided-step-form" onSubmit={handleCreateProject}>
            <div className="guided-step-intro">
              <h2 className="guided-step-title">Name your project</h2>
              <p className="guided-step-desc">A project groups your goals, backlog, and execution plan together.</p>
            </div>
            <div className="guided-field">
              <label className="guided-label" htmlFor="guided-project-name">Project name</label>
              <input
                id="guided-project-name"
                type="text"
                className="guided-input"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="e.g. My API, Mobile App, Internal Tools"
                autoFocus
                autoComplete="off"
              />
            </div>
            <div className="guided-field">
              <label className="guided-label" htmlFor="guided-project-desc">
                Description <span className="guided-label-optional">(optional)</span>
              </label>
              <textarea
                id="guided-project-desc"
                className="guided-textarea"
                value={projectDescription}
                onChange={(e) => setProjectDescription(e.target.value)}
                placeholder="What is this project about?"
                rows={3}
              />
            </div>
            {error && <div className="guided-error">{error}</div>}
            <div className="guided-actions">
              <button type="button" className="guided-btn-secondary" onClick={onExit}>
                Cancel
              </button>
              <button type="submit" className="guided-btn-primary" disabled={saving}>
                {saving ? 'Creating...' : 'Create project'}
                {!saving && <ArrowRight size={14} />}
              </button>
            </div>
          </form>
        )}

        {step === 2 && (
          <form className="guided-step-form" onSubmit={handleSubmitDirective}>
            <div className="guided-step-intro">
              <h2 className="guided-step-title">What do you want to build?</h2>
              <p className="guided-step-desc">
                Describe your first goal in plain language. The system will decompose it into backlog items automatically.
              </p>
            </div>
            <div className="guided-field">
              <label className="guided-label" htmlFor="guided-directive">Your directive</label>
              <textarea
                id="guided-directive"
                className="guided-textarea guided-textarea-lg"
                value={directive}
                onChange={(e) => setDirective(e.target.value)}
                placeholder={'e.g. "Build a user authentication system with email and OAuth support"'}
                rows={5}
                autoFocus
              />
            </div>
            {error && <div className="guided-error">{error}</div>}
            <div className="guided-actions">
              <button type="button" className="guided-btn-secondary" onClick={handleSkipDirective}>
                Skip for now
              </button>
              <button type="submit" className="guided-btn-primary" disabled={saving || !directive.trim()}>
                {saving ? 'Submitting...' : 'Submit directive'}
                {!saving && <ArrowRight size={14} />}
              </button>
            </div>
          </form>
        )}

        {step === 3 && (
          <div className="guided-step-form">
            <div className="guided-complete-icon">
              <CheckCircle size={40} strokeWidth={1.5} />
            </div>
            <div className="guided-step-intro">
              <h2 className="guided-step-title">
                {createdProject?.name} is ready
              </h2>
              <p className="guided-step-desc">
                {directive.trim()
                  ? 'Your directive has been submitted. The system will analyze and decompose it into backlog items shortly.'
                  : 'Your project is set up. Head to the directives page to describe what you want to build.'}
              </p>
            </div>
            <div className="guided-complete-links">
              <button className="guided-complete-link" onClick={() => navigate('/directives')}>
                <Target size={14} />
                <span>Go to Directives</span>
                <ArrowRight size={12} />
              </button>
              <button className="guided-complete-link" onClick={() => navigate('/backlog')}>
                <Play size={14} />
                <span>View Backlog</span>
                <ArrowRight size={12} />
              </button>
            </div>
            <div className="guided-actions guided-actions-center">
              <button type="button" className="guided-btn-primary" onClick={handleFinish}>
                Go to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

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
  const [showGuidedSetup, setShowGuidedSetup] = useState(false)

  const handleNewProject = useCallback(() => {
    setShowGuidedSetup(true)
  }, [])

  const handleExitSetup = useCallback(() => {
    setShowGuidedSetup(false)
  }, [])

  if (activeProject && !showGuidedSetup) {
    return <ActiveProjectDashboard />
  }

  if (showGuidedSetup) {
    return (
      <div className="dashboard-page">
        <GuidedSetup onExit={handleExitSetup} />
      </div>
    )
  }

  return <NoProjectDashboard onNewProject={handleNewProject} />
}

export default DashboardPage
