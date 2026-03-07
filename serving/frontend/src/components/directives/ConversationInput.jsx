import { useState, useCallback, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { INTENT_MODES } from '../../hooks/useConversation'

function ConversationInput({ onSubmit, submitting, disabled, commentMode, suggestedText, onSuggestedTextConsumed }) {
  const [text, setText] = useState('')
  const [mode] = useState(INTENT_MODES.AUTO)
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

  const handleSubmit = useCallback(() => {
    if (!text.trim() || submitting || disabled) return
    const effectiveMode = commentMode ? INTENT_MODES.NEW_WORK : mode
    onSubmit(text.trim(), effectiveMode)
    setText('')
  }, [text, mode, submitting, disabled, commentMode, onSubmit])

  const handleKeyDown = useCallback((e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  const placeholder = commentMode
    ? 'Add context, adjust priorities, or ask a question...'
    : 'Type a message or /start to begin work...'

  return (
    <div className="conv-input-container">
      <div className="conv-input-row">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
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

      <div className="conv-input-hint">
        <kbd>Cmd</kbd>+<kbd>Enter</kbd> to send
      </div>
    </div>
  )
}

export default ConversationInput
