import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext, INTENT_MODES } from '../contexts/ConversationContext'
import useIssues from '../hooks/useIssues'
import useDirectivePrompts from '../hooks/useDirectivePrompts'
import usePresence from '../hooks/usePresence'
import { createProject } from '../api/projects'
import { createGoal } from '../api/workmap'
import { Plus, ArrowRight, Target, Play, CheckCircle, X } from 'lucide-react'
import ConversationTimeline from '../components/directives/ConversationTimeline'
import ConversationInput from '../components/directives/ConversationInput'
import SummaryCards from '../components/dashboard/SummaryCards'
import PresenceBar from '../components/dashboard/PresenceBar'
import '../components/directives/Conversation.css'
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

function ActiveProjectDashboard() {
  const { activeProject } = useProjectContext()
  const {
    messages,
    submitting,
    pendingDirective,
    applying,
    lastCreatedGoal,
    submit,
    applyPending,
    rejectPending,
    retryProcessing,
  } = useConversationContext()
  const { stats } = useIssues({
    pollInterval: 15000,
    filters: { project_id: activeProject?.project_id },
  })
  const prompts = useDirectivePrompts(activeProject ? stats : null)
  const { users: presenceUsers } = usePresence(activeProject?.project_id || null)
  const [suggestedText, setSuggestedText] = useState('')

  const handleSuggestedTextConsumed = useCallback(() => {
    setSuggestedText('')
  }, [])

  const handleSubmit = useCallback(async (text, mode, options) => {
    await submit(text, mode, options)
  }, [submit])

  const handlePromoteToDirective = useCallback(async (msg) => {
    await submit(msg.content, INTENT_MODES.AUTO)
  }, [submit])

  return (
    <div className="dashboard-workspace">
      <div className="dashboard-conversation">
        {/* Empty state with prompts */}
        {messages.length === 0 && (
          <div className="dashboard-welcome-chat">
            <div className="dashboard-welcome-heading-row">
              <h2 className="dashboard-welcome-heading">{activeProject?.name}</h2>
              <PresenceBar users={presenceUsers} />
            </div>
            <p className="dashboard-welcome-desc">
              What would you like to do? Describe new work, shift priorities, or ask about status.
            </p>
            {prompts.length > 0 && (
              <div className="dashboard-prompt-chips">
                {prompts.map((prompt) => (
                  <button
                    key={prompt.text}
                    className="dashboard-prompt-chip"
                    onClick={() => setSuggestedText(prompt.text)}
                  >
                    {prompt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Conversation timeline */}
        <ConversationTimeline
          messages={messages}
          pendingDirective={pendingDirective}
          applying={applying}
          onApply={applyPending}
          onReject={rejectPending}
          onRetry={retryProcessing}
          onPromoteToDirective={handlePromoteToDirective}
        />

        {/* Input */}
        <ConversationInput
          onSubmit={handleSubmit}
          submitting={submitting}
          disabled={!!pendingDirective}
          suggestedText={suggestedText}
          onSuggestedTextConsumed={handleSuggestedTextConsumed}
        />
      </div>

      {/* Summary cards panel */}
      <SummaryCards />
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
