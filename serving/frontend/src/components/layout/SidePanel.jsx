import { useState, useRef, useEffect } from 'react'
import { useProjectContext } from '../../contexts/ProjectContext'
import { useConversationContext } from '../../contexts/ConversationContext'
import { Send, ChevronLeft, ChevronRight, MessageSquare } from 'lucide-react'
import './SidePanel.css'

// How many recent messages to show in the side panel preview
const SIDEPANEL_MAX_MESSAGES = 6

function SidePanel() {
  const { activeProject } = useProjectContext()
  const { messages, submitting, submit } = useConversationContext()
  const [collapsed, setCollapsed] = useState(false)
  const [message, setMessage] = useState('')
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)

  // Show the most recent messages (last N)
  const recentMessages = messages.slice(-SIDEPANEL_MAX_MESSAGES)

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [recentMessages])

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

  if (collapsed) {
    return (
      <div className="sidepanel-collapsed">
        <button
          className="sidepanel-expand-btn"
          onClick={() => setCollapsed(false)}
          title="Expand panel"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="sidepanel">
      <div className="sidepanel-header">
        <div className="sidepanel-header-info">
          <MessageSquare size={14} strokeWidth={1.5} />
          <span className="sidepanel-header-title">
            {activeProject ? activeProject.name : 'No project'}
          </span>
        </div>
        <button
          className="sidepanel-collapse-btn"
          onClick={() => setCollapsed(true)}
          title="Collapse panel"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      <div className="sidepanel-messages">
        {messages.length === 0 && (
          <div className="sidepanel-empty">
            {activeProject ? (
              <>
                <p className="sidepanel-empty-text">
                  Describe what you want to build or direct execution
                </p>
                <div className="sidepanel-prompts">
                  <button
                    className="sidepanel-prompt"
                    onClick={() => setMessage('Decompose my goals into work items')}
                  >
                    Decompose goals
                  </button>
                  <button
                    className="sidepanel-prompt"
                    onClick={() => setMessage('Focus on P0 items first')}
                  >
                    Focus on P0 items
                  </button>
                  <button
                    className="sidepanel-prompt"
                    onClick={() => setMessage('Review execution progress')}
                  >
                    Review progress
                  </button>
                </div>
              </>
            ) : (
              <p className="sidepanel-empty-text">
                Select a project to start
              </p>
            )}
          </div>
        )}

        {recentMessages.map((msg) => {
          // Normalize message format: useConversation uses {type, content, timestamp}
          // while old local state used {role, content, timestamp}
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

          // Skip purely internal/transient message types in the side panel
          if (isThinking) return null

          return (
            <div key={msg.id} className={`sidepanel-message sidepanel-message-${roleClass}`}>
              <p className="sidepanel-message-content">{msg.content}</p>
              <span className="sidepanel-message-time">
                {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      <div className="sidepanel-input-area">
        <div className="sidepanel-input-wrap">
          <textarea
            ref={inputRef}
            className="sidepanel-input"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeProject ? 'Type a directive...' : 'Select a project first'}
            disabled={!activeProject || submitting}
            rows={1}
          />
          <button
            className="sidepanel-send-btn"
            onClick={handleSend}
            disabled={!message.trim() || submitting || !activeProject}
            title="Send (Enter)"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default SidePanel
