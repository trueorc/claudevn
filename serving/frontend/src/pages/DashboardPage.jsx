import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext, INTENT_MODES } from '../contexts/ConversationContext'
import { useAuth } from '../contexts/auth/AuthContext'
import useIssues from '../hooks/useIssues'
import usePlanSummary from '../hooks/usePlanSummary'
import useTiming from '../hooks/useTiming'
import useSystemHealth from '../hooks/useSystemHealth'
import useDirectivePrompts from '../hooks/useDirectivePrompts'
import usePresence from '../hooks/usePresence'
import useChatTransition from '../hooks/useChatTransition'
import { Plus, ArrowRight } from 'lucide-react'
import ConversationTimeline from '../components/directives/ConversationTimeline'
import ConversationInput from '../components/directives/ConversationInput'
import LeftPanels from '../components/dashboard/LeftPanels'
import RightPanels from '../components/dashboard/RightPanels'
import PresenceBar from '../components/dashboard/PresenceBar'
import '../components/directives/Conversation.css'
import './DashboardPage.css'

function NoProjectDashboard() {
  const { projects, setActiveProject } = useProjectContext()
  const navigate = useNavigate()

  const handleSelectProject = (project) => {
    setActiveProject(project)
    navigate('/dashboard')
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-onboarding">
        <div className="dashboard-onboarding-welcome">
          <img src="/ClaudeVN-Logo-64x64.png" alt="ClaudeVN" width="40" height="40" className="dashboard-welcome-logo" />
          <h1 className="dashboard-onboarding-title">Welcome to ClaudeVN</h1>
          <p className="dashboard-onboarding-desc">
            I'm here to help you orchestrate AI-powered development. Tell me about your project to get started.
          </p>
        </div>

        <div className="dashboard-onboarding-actions">
          <button className="dashboard-onboarding-btn dashboard-onboarding-btn-primary" onClick={() => navigate('/projects?create=true')}>
            <Plus size={16} />
            Create a new project
          </button>

          {projects.length > 0 && (
            <div className="dashboard-onboarding-existing">
              <span className="dashboard-onboarding-or">or open an existing project</span>
              <div className="dashboard-onboarding-projects">
                {projects.map((project) => (
                  <button
                    key={project.project_id}
                    className="dashboard-onboarding-project"
                    onClick={() => handleSelectProject(project)}
                  >
                    <span
                      className="dashboard-project-dot"
                      style={{ background: project.color || 'var(--primary)' }}
                    />
                    {project.name}
                    <ArrowRight size={12} className="dashboard-onboarding-project-arrow" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ActiveProjectDashboard() {
  const { activeProject, projects, setActiveProject } = useProjectContext()
  const { user } = useAuth()
  const navigate = useNavigate()
  const {
    messages,
    submitting,
    pendingDirective,
    applying,
    submit,
    applyPending,
    rejectPending,
    retryProcessing,
  } = useConversationContext()

  const projectId = activeProject?.project_id

  // Data hooks — shared across panels
  const { stats } = useIssues({
    pollInterval: 15000,
    filters: { project_id: projectId },
  })
  const { data: planData } = usePlanSummary(projectId, { pollInterval: 15000 })
  const { aggregates, totalWorkItems } = useTiming(projectId, { pollInterval: 30000 })
  const { health, overallStatus, loading: healthLoading } = useSystemHealth({ pollInterval: 30000 })
  const { users: presenceUsers } = usePresence(projectId || null, activeProject?.name || null)
  const prompts = useDirectivePrompts(activeProject ? stats : null)
  const { transitionClass, scrollPositionRef } = useChatTransition()

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

  const handleNewProject = useCallback(() => {
    navigate('/projects?create=true')
  }, [navigate])

  return (
    <div className="dashboard-command-center">
      {/* Left column — Operations */}
      <div className="dashboard-col-left">
        <LeftPanels
          projects={projects}
          activeProject={activeProject}
          onSelectProject={setActiveProject}
          onNewProject={handleNewProject}
          planData={planData}
          health={health}
          overallStatus={overallStatus}
          healthLoading={healthLoading}
        />
      </div>

      {/* Center column — Conversation */}
      <div className={`dashboard-col-center${transitionClass === 'chat-transition-to-center' ? ' dashboard-col-center-enter' : ''}`}>
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

        <ConversationTimeline
          messages={messages}
          currentUserId={user?.sub}
          pendingDirective={pendingDirective}
          applying={applying}
          onApply={applyPending}
          onReject={rejectPending}
          onRetry={retryProcessing}
          onPromoteToDirective={handlePromoteToDirective}
        />

        <ConversationInput
          onSubmit={handleSubmit}
          submitting={submitting}
          disabled={!!pendingDirective}
          suggestedText={suggestedText}
          onSuggestedTextConsumed={handleSuggestedTextConsumed}
        />
      </div>

      {/* Right column — Analytics */}
      <div className="dashboard-col-right">
        <RightPanels
          stats={stats}
          aggregates={aggregates}
          totalWorkItems={totalWorkItems}
          presenceUsers={presenceUsers}
        />
      </div>
    </div>
  )
}

function DashboardPage() {
  const { activeProject } = useProjectContext()

  if (activeProject) {
    return <ActiveProjectDashboard />
  }

  return <NoProjectDashboard />
}

export default DashboardPage
