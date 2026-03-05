import { useState, useRef, useEffect } from 'react'
import { useProjectContext } from '../../contexts/ProjectContext'
import { Send, ChevronLeft, ChevronRight, MessageSquare } from 'lucide-react'
import './SidePanel.css'

function SidePanel() {
  const { activeProject } = useProjectContext()
  const [collapsed, setCollapsed] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [sending, setSending] = useState(false)
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!message.trim() || sending) return

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: message.trim(),
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setMessage('')
    setSending(true)

    // Simulate sending — actual integration with directives API
    // will come with issue #168 (persistent conversation)
    setTimeout(() => {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'system',
        content: 'Message received. Conversation persistence coming soon.',
        timestamp: new Date(),
      }])
      setSending(false)
    }, 500)
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

        {messages.map((msg) => (
          <div key={msg.id} className={`sidepanel-message sidepanel-message-${msg.role}`}>
            <p className="sidepanel-message-content">{msg.content}</p>
            <span className="sidepanel-message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
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
            disabled={!activeProject || sending}
            rows={1}
          />
          <button
            className="sidepanel-send-btn"
            onClick={handleSend}
            disabled={!message.trim() || sending || !activeProject}
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
