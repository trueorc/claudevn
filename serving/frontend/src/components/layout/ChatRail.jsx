import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectContext } from '../../contexts/ProjectContext'
import { useConversationContext } from '../../contexts/ConversationContext'
import useIssues from '../../hooks/useIssues'
import useDirectivePrompts from '../../hooks/useDirectivePrompts'
import useChatTransition from '../../hooks/useChatTransition'
import useEventStream from '../../hooks/useEventStream'
import { Send, ChevronLeft, ChevronRight, MessageSquare, ExternalLink, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import './ChatRail.css'

const CHATRAIL_MAX_MESSAGES = 500

// Message types shown in the sidebar rail — keep it focused on completed
// outcomes and user messages. Full detail lives in the Control Center.
const CHATRAIL_VISIBLE_TYPES = new Set([
  'user',
  'assistant',
  'goal_complete',
  'goal_processing',
  'directive_applied',
  'directive_rejected',
  'error',
])

function RailProjectHeader() {
  const { activeProject } = useProjectContext()
  const navigate = useNavigate()

  return (
    <button
      className="rail-project-selector"
      onClick={() => navigate('/projects')}
      title="Switch project"
    >
      <span className="rail-project-name">
        {activeProject ? activeProject.name : 'Select project'}
      </span>
      <ChevronRight size={14} />
    </button>
  )
}

function ChatRail() {
  const { activeProject } = useProjectContext()
  const { messages, submitting, submit, sendTypingStatus, activeGoalId, activeGoalTitle } = useConversationContext()
  const [collapsed, setCollapsed] = useState(false)
  const [message, setMessage] = useState('')
  const [unreadCount, setUnreadCount] = useState(0)
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const prevMessageCountRef = useRef(messages.length)
  const navigate = useNavigate()
  const { transitionClass, isDashboard, saveScrollPosition } = useChatTransition()

  // Load issue stats for context-aware prompts (only when a project is active)
  const { stats } = useIssues({ useWebSocket: !!activeProject, pollInterval: activeProject ? 30000 : 0 })
  const prompts = useDirectivePrompts(activeProject ? stats : null)

  // Pipeline progress — tracks active decomposition steps via SSE
  const [pipelineSteps, setPipelineSteps] = useState([])
  const [pipelineActive, setPipelineActive] = useState(false)

  const STEP_LABELS = {
    llm_decompose: 'Decomposing',
    codebase_analysis: 'Analyzing codebase',
    build_work_units: 'Building work units',
    resolve_dependencies: 'Resolving dependencies',
    reconcile_plan: 'Reconciling plan',
    validate: 'Validating',
    score_quality: 'Scoring quality',
    analyze_environment: 'Analyzing environment',
  }

  useEventStream({
    patterns: ['decomposition.*'],
    projectId: activeProject?.project_id,
    enabled: !!activeProject,
    onEvent: useCallback((event) => {
      if (event.event === 'decomposition.started') {
        setPipelineActive(true)
        setPipelineSteps([])
      }
      if (event.event === 'decomposition.step_started') {
        setPipelineSteps(prev => [
          ...prev.filter(s => s.name !== event.step_name),
          { name: event.step_name, status: 'running' },
        ])
      }
      if (event.event === 'decomposition.step_completed') {
        setPipelineSteps(prev => prev.map(s =>
          s.name === event.step_name
            ? { ...s, status: 'completed', duration_ms: event.duration_ms, detail: event.detail }
            : s
        ))
      }
      if (event.event === 'decomposition.step_failed') {
        setPipelineSteps(prev => prev.map(s =>
          s.name === event.step_name ? { ...s, status: 'failed', error: event.error } : s
        ))
      }
      if (event.event === 'decomposition.completed') {
        setPipelineActive(false)
      }
    }, []),
  })

  const recentMessages = messages
    .filter(m => CHATRAIL_VISIBLE_TYPES.has(m.type))
    .slice(-CHATRAIL_MAX_MESSAGES)

  // Track unread messages when collapsed
  useEffect(() => {
    if (collapsed && messages.length > prevMessageCountRef.current) {
      setUnreadCount(prev => prev + (messages.length - prevMessageCountRef.current))
    }
    prevMessageCountRef.current = messages.length
  }, [messages.length, collapsed])

  // Clear unread count when expanding
  useEffect(() => {
    if (!collapsed) {
      setUnreadCount(0)
    }
  }, [collapsed])

  // Auto-scroll when new messages arrive
  useEffect(() => {
    if (!isDashboard && !collapsed) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [recentMessages, isDashboard, collapsed])

  const handleSend = async () => {
    if (!message.trim() || submitting || !activeProject) return
    const text = message.trim()
    setMessage('')
    sendTypingStatus?.(false)
    await submit(text)
  }

  const handleInputChange = (e) => {
    setMessage(e.target.value)
    sendTypingStatus?.(e.target.value.length > 0)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Save scroll position when transitioning to dashboard
  const messagesContainerRef = useRef(null)
  useEffect(() => {
    if (isDashboard && messagesContainerRef.current) {
      saveScrollPosition(messagesContainerRef.current.scrollTop)
    }
  }, [isDashboard, saveScrollPosition])

  // Build class list based on state — always render so CSS transitions can fire
  const railClasses = [
    'chat-rail',
    isDashboard ? 'chat-rail-hidden' : '',
    !isDashboard && collapsed ? 'chat-rail-collapsed' : '',
    !isDashboard && !collapsed && transitionClass === 'chat-transition-to-sidebar' ? 'chat-rail-enter' : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={railClasses}>
      {/* Collapsed icon button — visible only when collapsed and not on dashboard */}
      {!isDashboard && collapsed && (
        <button
          className="chat-rail-expand-btn"
          onClick={() => setCollapsed(false)}
          title="Expand chat"
        >
          <MessageSquare size={16} />
          {unreadCount > 0 && (
            <span className="chat-rail-unread">{unreadCount > 9 ? '9+' : unreadCount}</span>
          )}
        </button>
      )}

      {/* Full rail content — visible only when expanded and not on dashboard */}
      {!isDashboard && !collapsed && (
        <>
          <RailProjectHeader />

          {activeGoalId && (
            <div className="chat-rail-goal-context">
              <span className="chat-rail-goal-label">Goal context:</span>
              <span className="chat-rail-goal-title">{activeGoalTitle || activeGoalId}</span>
            </div>
          )}

          <div className="chat-rail-header">
            <button
              className="chat-rail-full-link"
              onClick={() => navigate('/dashboard')}
              title="Open Control Center"
            >
              <ExternalLink size={12} />
              <span>Full view</span>
            </button>
            <button
              className="chat-rail-collapse-btn"
              onClick={() => setCollapsed(true)}
              title="Collapse chat"
            >
              <ChevronLeft size={14} />
            </button>
          </div>

          {/* Pipeline progress — shows during active decomposition */}
          {(pipelineActive || pipelineSteps.length > 0) && (
            <div className="chat-rail-pipeline">
              <div className="chat-rail-pipeline-header">
                {pipelineActive ? <Loader2 size={12} className="chat-rail-spin" /> : <CheckCircle2 size={12} />}
                <span>{pipelineActive ? 'Decomposing...' : 'Decomposition complete'}</span>
              </div>
              <div className="chat-rail-pipeline-steps">
                {pipelineSteps.map(s => (
                  <div key={s.name} className={`chat-rail-step chat-rail-step--${s.status}`}>
                    {s.status === 'running' && <Loader2 size={10} className="chat-rail-spin" />}
                    {s.status === 'completed' && <CheckCircle2 size={10} />}
                    {s.status === 'failed' && <XCircle size={10} />}
                    <span>{STEP_LABELS[s.name] || s.name}</span>
                    {s.duration_ms != null && <span className="chat-rail-step-time">{s.duration_ms < 1000 ? `${s.duration_ms}ms` : `${Math.round(s.duration_ms / 1000)}s`}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="chat-rail-messages" ref={messagesContainerRef}>
            {messages.length === 0 && (
              <div className="chat-rail-empty">
                {activeProject ? (
                  <>
                    <p className="chat-rail-empty-text">
                      Describe what you want to build
                    </p>
                    {prompts.length > 0 && (
                      <div className="chat-rail-prompts">
                        {prompts.map((prompt) => (
                          <button
                            key={prompt.text}
                            className="chat-rail-prompt"
                            onClick={() => setMessage(prompt.text)}
                          >
                            {prompt.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p className="chat-rail-empty-text">Select a project</p>
                )}
              </div>
            )}

            {recentMessages.map((msg) => {
              const isUser = msg.type === 'user' || msg.role === 'user'
              const isAssistant = msg.type === 'assistant'
              const isError = msg.type === 'error'
              const roleClass = isUser ? 'user' : isAssistant ? 'assistant' : isError ? 'error' : 'system'
              const timestamp = msg.timestamp
                ? (typeof msg.timestamp === 'string'
                    ? new Date(msg.timestamp)
                    : msg.timestamp instanceof Date
                      ? msg.timestamp
                      : new Date())
                : new Date()

              return (
                <div key={msg.id} className={`chat-rail-message chat-rail-message-${roleClass}`}>
                  <p className="chat-rail-message-content">{msg.content}</p>
                  <span className="chat-rail-message-time">
                    {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-rail-input-area">
            <div className="chat-rail-input-wrap">
              <textarea
                ref={inputRef}
                className="chat-rail-input"
                value={message}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={
                  !activeProject
                    ? 'Select a project'
                    : activeGoalId
                      ? `Refine "${activeGoalTitle || 'goal'}..." `
                      : 'Type a directive...'
                }
                disabled={!activeProject || submitting}
                rows={1}
              />
              <button
                className="chat-rail-send-btn"
                onClick={handleSend}
                disabled={!message.trim() || submitting || !activeProject}
                title="Send (Enter)"
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default ChatRail
