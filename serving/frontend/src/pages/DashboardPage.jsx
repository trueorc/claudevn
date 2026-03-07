import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext, INTENT_MODES } from '../contexts/ConversationContext'
import useIssues from '../hooks/useIssues'
import useDirectivePrompts from '../hooks/useDirectivePrompts'
import usePresence from '../hooks/usePresence'
import { Plus, ArrowRight } from 'lucide-react'
import ConversationTimeline from '../components/directives/ConversationTimeline'
import ConversationInput from '../components/directives/ConversationInput'
import SummaryCards from '../components/dashboard/SummaryCards'
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

  if (activeProject) {
    return <ActiveProjectDashboard />
  }

  return <NoProjectDashboard />
}

export default DashboardPage
