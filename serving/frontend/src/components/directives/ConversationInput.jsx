import { useState, useCallback, useRef, useEffect } from 'react'
import { Send, ChevronDown, ChevronRight } from 'lucide-react'
import { INTENT_MODES } from '../../hooks/useConversation'

const PRIORITIES = [
  { value: '', label: 'Priority' },
  { value: 'P0', label: 'P0 - Critical' },
  { value: 'P1', label: 'P1 - High' },
  { value: 'P2', label: 'P2 - Medium' },
  { value: 'P3', label: 'P3 - Low' },
]

const MODE_LABELS = {
  [INTENT_MODES.AUTO]: 'Auto',
  [INTENT_MODES.NEW_WORK]: 'New Work',
  [INTENT_MODES.DIRECTIVE]: 'Directive',
}

function ConversationInput({ onSubmit, submitting, disabled, commentMode, suggestedText, onSuggestedTextConsumed }) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState(INTENT_MODES.AUTO)
  const [showOptions, setShowOptions] = useState(false)
  const [priority, setPriority] = useState('')
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
    onSubmit(text.trim(), effectiveMode, { priority: priority || undefined })
    setText('')
    setPriority('')
  }, [text, mode, priority, submitting, disabled, commentMode, onSubmit])

  const handleKeyDown = useCallback((e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  const placeholder = commentMode
    ? 'Add context, adjust priorities, or ask a question...'
    : mode === INTENT_MODES.DIRECTIVE
      ? 'e.g. "Focus on testing for the API domain"'
      : mode === INTENT_MODES.NEW_WORK
        ? 'Describe what you want to achieve...'
        : 'Tell me what you need \u2014 new work, priority shift, or a question...'

  return (
    <div className="conv-input-container">
      {!commentMode && (
        <div className="conv-mode-bar">
          {Object.entries(MODE_LABELS).map(([key, label]) => (
            <button
              key={key}
              className={`conv-mode-chip ${mode === key ? 'active' : ''}`}
              onClick={() => setMode(key)}
              disabled={submitting}
            >
              {label}
            </button>
          ))}
        </div>
      )}

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

      {!commentMode && mode !== INTENT_MODES.DIRECTIVE && (
        <div className="conv-options-row">
          <button
            className="conv-options-toggle"
            onClick={() => setShowOptions(!showOptions)}
            disabled={submitting}
          >
            {showOptions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Options
          </button>
          {showOptions && (
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="conv-option-select"
              disabled={submitting}
            >
              {PRIORITIES.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          )}
        </div>
      )}

      <div className="conv-input-hint">
        <kbd>Cmd</kbd>+<kbd>Enter</kbd> to send
      </div>
    </div>
  )
}

export default ConversationInput
