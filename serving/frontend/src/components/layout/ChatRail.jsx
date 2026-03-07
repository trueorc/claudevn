import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useProjectContext } from '../../contexts/ProjectContext'
import { useConversationContext } from '../../contexts/ConversationContext'
import useIssues from '../../hooks/useIssues'
import useDirectivePrompts from '../../hooks/useDirectivePrompts'
import { Send, ChevronLeft, MessageSquare, ExternalLink } from 'lucide-react'
import './ChatRail.css'

const CHATRAIL_MAX_MESSAGES = 10

function ChatRail() {
  const { activeProject } = useProjectContext()
  const { messages, submitting, submit } = useConversationContext()
  const [collapsed, setCollapsed] = useState(false)
  const [message, setMessage] = useState('')
  const [unreadCount, setUnreadCount] = useState(0)
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const prevMessageCountRef = useRef(messages.length)
  const location = useLocation()
  const navigate = useNavigate()

  // Load issue stats for context-aware prompts (only when a project is active)
  const { stats } = useIssues({ useWebSocket: !!activeProject, pollInterval: activeProject ? 30000 : 0 })
  const prompts = useDirectivePrompts(activeProject ? stats : null)

  const recentMessages = messages.slice(-CHATRAIL_MAX_MESSAGES)
  const isDashboard = location.pathname === '/dashboard' || location.pathname === '/'

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
    await submit(text)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Build class list based on state — always render so CSS transitions can fire
  const railClasses = [
    'chat-rail',
    isDashboard ? 'chat-rail-hidden' : '',
    !isDashboard && collapsed ? 'chat-rail-collapsed' : '',
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

          <div className="chat-rail-messages">
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
              const isError = msg.type === 'error'
              const isThinking = msg.type === 'thinking'
              const roleClass = isUser ? 'user' : isError ? 'error' : 'system'
              const timestamp = msg.timestamp
                ? (typeof msg.timestamp === 'string'
                    ? new Date(msg.timestamp)
                    : msg.timestamp instanceof Date
                      ? msg.timestamp
                      : new Date())
                : new Date()

              if (isThinking) return null

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
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={activeProject ? 'Type a directive...' : 'Select a project'}
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
