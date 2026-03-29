import { useState, useCallback, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { INTENT_MODES } from '../../hooks/useConversation'
import ConversationContext from '../../contexts/ConversationContext'
import { useContext } from 'react'

const MODE_OPTIONS = [
  { value: INTENT_MODES.CHAT, label: 'Chat' },
  { value: INTENT_MODES.NEW_WORK, label: 'New Work' },
  { value: INTENT_MODES.DIRECTIVE, label: 'Directive' },
]

const PLACEHOLDERS = {
  [INTENT_MODES.CHAT]: 'Type a message or /start to begin work...',
  [INTENT_MODES.NEW_WORK]: 'Describe what you want built or changed...',
  [INTENT_MODES.DIRECTIVE]: 'Focus on testing, deprioritize styling...',
}

function ConversationInput({ onSubmit, submitting, disabled, commentMode, placeholder: customPlaceholder, suggestedText, onSuggestedTextConsumed }) {
  const conversationCtx = useContext(ConversationContext)
  const sendTypingStatus = conversationCtx?.sendTypingStatus
  const [text, setText] = useState('')
  const [mode, setMode] = useState(INTENT_MODES.CHAT)
  const [showOptions, setShowOptions] = useState(false)
  const [priority, setPriority] = useState(undefined)
  const textareaRef = useRef(null)

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`
    }
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [text, adjustHeight])

  // Populate the textarea when a suggested prompt is clicked externally
  useEffect(() => {
    if (suggestedText) {
      setText(suggestedText)
      textareaRef.current?.focus()
      onSuggestedTextConsumed?.()
    }
  }, [suggestedText]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleTextChange = useCallback((e) => {
    setText(e.target.value)
    sendTypingStatus?.(e.target.value.length > 0)
  }, [sendTypingStatus])

  const handleSubmit = useCallback(() => {
    if (!text.trim() || submitting || disabled) return
    const effectiveMode = commentMode ? INTENT_MODES.NEW_WORK : mode
    sendTypingStatus?.(false)
    onSubmit(text.trim(), effectiveMode, { priority })
    setText('')
  }, [text, mode, submitting, disabled, commentMode, priority, onSubmit, sendTypingStatus])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  const placeholder = customPlaceholder
    || (commentMode
      ? 'Add context, adjust priorities, or ask a question...'
      : PLACEHOLDERS[mode] || PLACEHOLDERS[INTENT_MODES.CHAT])

  const showModeButtons = !commentMode
  const showOptionsToggle = !commentMode && mode !== INTENT_MODES.DIRECTIVE

  return (
    <div className="conv-input-container">
      {showModeButtons && (
        <div className="conv-mode-bar">
          {MODE_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`conv-mode-chip${mode === opt.value ? ' active' : ''}`}
              onClick={() => setMode(opt.value)}
              disabled={submitting}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      <div className="conv-input-row">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={submitting || disabled}
          rows={1}
          className="conv-textarea"
        />
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || submitting || disabled}
          className="conv-send-btn"
        >
          {submitting ? (
            <span className="directive-spinner" />
          ) : (
            <Send size={16} />
          )}
        </button>
      </div>

      {showOptionsToggle && (
        <div className="conv-options-row">
          <button
            className="conv-options-toggle"
            onClick={() => setShowOptions(v => !v)}
          >
            Options
          </button>
          {showOptions && (
            <select
              value={priority || ''}
              onChange={(e) => setPriority(e.target.value || undefined)}
              className="conv-option-select"
            >
              <option value="">Priority</option>
              <option value="P0">P0 - Critical</option>
              <option value="P1">P1 - High</option>
              <option value="P2">P2 - Normal</option>
            </select>
          )}
        </div>
      )}

      <div className="conv-input-hint">
        <kbd>Enter</kbd> to send, <kbd>Shift</kbd>+<kbd>Enter</kbd> for new line
      </div>
    </div>
  )
}

export default ConversationInput
