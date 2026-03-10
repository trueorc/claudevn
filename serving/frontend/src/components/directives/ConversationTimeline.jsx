import { useRef, useEffect, useState, useCallback } from 'react'
import { Loader, Check, X, AlertCircle, ArrowRight, Sparkles, Target, FileText, Clock, RefreshCw, Bot, ChevronDown } from 'lucide-react'
import { MSG_TYPES } from '../../hooks/useConversation'
import { getAvatarColor, getInitials } from '../common/UserAvatar'
import GoalCompletionCard from './GoalCompletionCard'

const STAGE_LABELS = {
  queued: 'Queuing work...',
  decomposing: 'Decomposing goal...',
  characterizing: 'Characterizing work items...',
  creating_issues: 'Creating backlog items...',
  complete: 'Done',
  failed: 'Failed',
}

/** Ordered stages for the progress stepper (excludes terminal states). */
const STAGE_ORDER = ['queued', 'decomposing', 'characterizing', 'creating_issues']

function formatTime(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// Classification: which message types render as compact inline indicators
// vs full card components.
// ---------------------------------------------------------------------------

const COMPACT_TYPES = new Set([
  MSG_TYPES.THINKING,
  MSG_TYPES.GOAL_CREATED,
  MSG_TYPES.DIRECTIVE_APPLIED,
  MSG_TYPES.DIRECTIVE_REJECTED,
  MSG_TYPES.SYSTEM,
  MSG_TYPES.ERROR,
])

const CHAT_TYPES = new Set([MSG_TYPES.USER, MSG_TYPES.ASSISTANT])

function isStatusMessage(msg) {
  return !CHAT_TYPES.has(msg.type)
}

// ---------------------------------------------------------------------------
// Chat message components (unchanged)
// ---------------------------------------------------------------------------

function UserMessage({ msg, currentUserId, onPromoteToDirective }) {
  const senderId = msg.userId
  const isCurrentUser = !senderId || senderId === currentUserId
  const isAI = senderId === 'ai' || msg.displayName === 'AI'

  if (isAI) {
    return (
      <div className="conv-msg conv-msg-ai">
        <div className="conv-msg-sender">
          <span className="conv-msg-sender-avatar conv-ai-avatar">AI</span>
          <span className="conv-msg-sender-name">AI</span>
        </div>
        <div className="conv-msg-bubble conv-bubble-ai">
          <p className="conv-msg-text">{msg.content}</p>
          <span className="conv-msg-time">{formatTime(msg.timestamp)}</span>
        </div>
      </div>
    )
  }

  if (isCurrentUser) {
    const color = currentUserId ? getAvatarColor(currentUserId) : null
    return (
      <div className="conv-msg conv-msg-user">
        <div
          className="conv-msg-bubble conv-bubble-user"
          style={color ? { backgroundColor: color } : undefined}
        >
          <p className="conv-msg-text">{msg.content}</p>
          <span className="conv-msg-time">{formatTime(msg.timestamp)}</span>
        </div>
        {onPromoteToDirective && (
          <button
            className="conv-promote-btn"
            onClick={() => onPromoteToDirective(msg)}
            title="Submit as directive"
          >
            <Target size={12} />
          </button>
        )}
      </div>
    )
  }

  // Other user
  const color = getAvatarColor(senderId)
  const displayName = msg.displayName || senderId
  const initials = getInitials(displayName)

  return (
    <div className="conv-msg conv-msg-other">
      <div className="conv-msg-sender">
        <span className="conv-msg-sender-avatar" style={{ backgroundColor: color }}>
          {initials}
        </span>
        <span className="conv-msg-sender-name">{displayName}</span>
      </div>
      <div className="conv-msg-bubble conv-bubble-other" style={{ borderColor: color }}>
        <p className="conv-msg-text">{msg.content}</p>
        <span className="conv-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function AssistantMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-ai">
      <div className="conv-msg-sender">
        <span className="conv-msg-sender-avatar conv-ai-avatar">
          <Bot size={12} />
        </span>
        <span className="conv-msg-sender-name">{msg.displayName || 'Claude'}</span>
      </div>
      <div className="conv-msg-bubble conv-bubble-ai">
        <p className="conv-msg-text">{msg.content}</p>
        <span className="conv-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Compact status line — single-line inline indicator for simple status msgs
// ---------------------------------------------------------------------------

function CompactStatusLine({ icon, label, className, time }) {
  return (
    <div className={`conv-status-line ${className || ''}`}>
      {icon}
      <span className="conv-status-label">{label}</span>
      {time && <span className="conv-status-time">{time}</span>}
    </div>
  )
}

function renderCompactStatus(msg) {
  switch (msg.type) {
    case MSG_TYPES.THINKING:
      return (
        <CompactStatusLine
          key={msg.id}
          icon={<Loader size={11} className="conv-spinner" />}
          label={msg.content}
          className="conv-status-thinking"
          time={formatTime(msg.timestamp)}
        />
      )
    case MSG_TYPES.GOAL_CREATED:
      return (
        <CompactStatusLine
          key={msg.id}
          icon={<Sparkles size={11} className="conv-icon-goal" />}
          label="New work created"
          className="conv-status-goal"
          time={formatTime(msg.timestamp)}
        />
      )
    case MSG_TYPES.DIRECTIVE_APPLIED: {
      const intent = msg.directive?.interpretation?.detected_intent
      const summary = msg.directive?.interpretation?.summary
      return (
        <CompactStatusLine
          key={msg.id}
          icon={<Check size={11} className="conv-icon-success" />}
          label={summary ? `Applied — ${summary}` : `Changes applied${intent ? ` (${intent})` : ''}`}
          className="conv-status-applied"
          time={formatTime(msg.timestamp)}
        />
      )
    }
    case MSG_TYPES.DIRECTIVE_REJECTED:
      return (
        <CompactStatusLine
          key={msg.id}
          icon={<X size={11} className="conv-icon-rejected" />}
          label="Changes rejected"
          className="conv-status-rejected"
          time={formatTime(msg.timestamp)}
        />
      )
    case MSG_TYPES.ERROR:
      return (
        <CompactStatusLine
          key={msg.id}
          icon={<AlertCircle size={11} className="conv-icon-error" />}
          label={msg.content}
          className="conv-status-error"
          time={formatTime(msg.timestamp)}
        />
      )
    case MSG_TYPES.SYSTEM: {
      const parts = msg.content.split(/\*\*(.*?)\*\*/g)
      return (
        <div key={msg.id} className="conv-status-line conv-status-system">
          <span className="conv-status-label">
            {parts.map((part, i) => i % 2 === 1 ? <strong key={i}>{part}</strong> : part)}
          </span>
          <span className="conv-status-time">{formatTime(msg.timestamp)}</span>
        </div>
      )
    }
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Full card components (for interactive / multi-line status messages)
// ---------------------------------------------------------------------------

function ElapsedTime({ startedAt }) {
  const [elapsed, setElapsed] = useState('')

  useEffect(() => {
    if (!startedAt) return
    const start = new Date(startedAt).getTime()
    const tick = () => {
      const secs = Math.floor((Date.now() - start) / 1000)
      if (secs < 60) setElapsed(`${secs}s`)
      else setElapsed(`${Math.floor(secs / 60)}m ${secs % 60}s`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])

  if (!elapsed) return null
  return <span className="conv-elapsed">{elapsed}</span>
}

function GoalProcessingMessage({ msg, onRetry }) {
  const label = STAGE_LABELS[msg.stage] || 'Processing...'
  const activeIdx = STAGE_ORDER.indexOf(msg.stage)

  if (msg.isTimedOut) {
    return (
      <div className="conv-msg conv-msg-system">
        <div className="conv-msg-bubble conv-bubble-system conv-timed-out">
          <div className="conv-msg-header">
            <Clock size={14} className="conv-icon-warning" />
            <span className="conv-msg-label">Processing Timed Out</span>
          </div>
          <p className="conv-timeout-text">
            Processing has not completed after 5 minutes. The operation may still be running on the server.
          </p>
          {onRetry && (
            <div className="conv-timeout-actions">
              <button className="conv-btn conv-btn-retry" onClick={onRetry}>
                <RefreshCw size={14} /> Retry
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-processing-card">
        <div className="conv-processing-header">
          <Loader size={14} className="conv-spinner" />
          <span className="conv-processing-label">{label}</span>
          <ElapsedTime startedAt={msg.startedAt} />
        </div>
        <div className="conv-stage-stepper">
          {STAGE_ORDER.map((stage, i) => {
            const done = activeIdx > i
            const active = activeIdx === i
            return (
              <div
                key={stage}
                className={`conv-stage-step${done ? ' done' : ''}${active ? ' active' : ''}`}
              >
                <div className="conv-stage-dot">
                  {done ? <Check size={10} /> : active ? <Loader size={10} className="conv-spinner" /> : null}
                </div>
                <span className="conv-stage-name">{STAGE_LABELS[stage].replace('...', '')}</span>
              </div>
            )
          })}
        </div>
        {msg.isStalled && (
          <div className="conv-stalled-warning">
            <Clock size={12} className="conv-icon-warning" />
            <span>This is taking longer than expected...</span>
          </div>
        )}
      </div>
    </div>
  )
}

function GoalCompleteMessage({ msg }) {
  const result = msg.result
  const issues = result?.issues_created || result?.issues || []

  return (
    <GoalCompletionCard
      issues={issues}
      reasoning={result?.reasoning}
      startedAt={msg.startedAt}
    />
  )
}

function WeightChangeRow({ adj }) {
  const current = adj.current_weight != null ? `${(adj.current_weight * 100).toFixed(0)}%` : 'default'
  const proposed = `${(adj.proposed_weight * 100).toFixed(0)}%`
  const isUp = adj.current_weight != null ? adj.proposed_weight > adj.current_weight : adj.proposed_weight > 0.5

  return (
    <div className="conv-weight-row">
      <span className="conv-weight-label">{adj.category}/{adj.key}</span>
      <span className="conv-weight-values">
        <span className="conv-weight-current">{current}</span>
        <ArrowRight size={10} />
        <span className={`conv-weight-proposed ${isUp ? 'increase' : 'decrease'}`}>{proposed}</span>
      </span>
    </div>
  )
}

function DirectivePreviewMessage({ msg, onApply, onReject, applying, isPending }) {
  const directive = msg.directive
  const interp = directive?.interpretation
  if (!interp) return null

  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-directive">
        <div className="conv-msg-header">
          <Target size={14} className="conv-icon-directive" />
          <span className="conv-msg-label">{msg.content}</span>
          <span className={`conv-intent-badge intent-${interp.detected_intent}`}>
            {interp.detected_intent}
          </span>
        </div>

        {interp.summary && <p className="conv-directive-summary">{interp.summary}</p>}

        {interp.weight_adjustments?.length > 0 && (
          <div className="conv-directive-section">
            <h4 className="conv-section-title">Weight Changes</h4>
            {interp.weight_adjustments.map((adj, i) => (
              <WeightChangeRow key={i} adj={adj} />
            ))}
          </div>
        )}

        {interp.policy_adjustments?.length > 0 && (
          <div className="conv-directive-section">
            <h4 className="conv-section-title">Policy Changes</h4>
            {interp.policy_adjustments.map((adj, i) => (
              <div key={i} className="conv-policy-row">
                <span className={`conv-policy-action action-${adj.action}`}>{adj.action}</span>
                <span className="conv-policy-name">{adj.rule_name}</span>
                {adj.rule_description && (
                  <span className="conv-policy-desc">{adj.rule_description}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {isPending && (
          <div className="conv-directive-actions">
            <button className="conv-btn conv-btn-reject" onClick={onReject} disabled={applying}>
              <X size={14} /> Reject
            </button>
            <button className="conv-btn conv-btn-apply" onClick={onApply} disabled={applying}>
              {applying ? <Loader size={14} className="conv-spinner" /> : <Check size={14} />}
              {applying ? 'Applying...' : 'Apply'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function AttentionMessage({ msg }) {
  const isConflict = !!msg.metadata?.conflict_type
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-attention-card">
        <div className="conv-msg-header">
          <AlertCircle size={14} className="conv-icon-attention" />
          <span className="conv-msg-label">
            {isConflict ? 'Potential conflict detected' : msg.content}
          </span>
        </div>
        {isConflict && (
          <p className="conv-attention-detail">{msg.content}</p>
        )}
        {!isConflict && msg.metadata?.detail && (
          <p className="conv-attention-detail">{msg.metadata.detail}</p>
        )}
        {isConflict && (
          <div className="conv-attention-actions">
            <button className="conv-btn conv-btn-action">Keep mine</button>
            <button className="conv-btn conv-btn-action">Discuss</button>
            <button className="conv-btn conv-btn-dismiss-action">Not a conflict</button>
          </div>
        )}
        {!isConflict && msg.metadata?.actions?.length > 0 && (
          <div className="conv-attention-actions">
            {msg.metadata.actions.map((action, i) => (
              <button key={i} className="conv-btn conv-btn-action">{action.label}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PromoteSuggestionMessage({ msg, onPromote, onDismiss }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-promote-suggestion">
        <div className="conv-msg-header">
          <Sparkles size={14} className="conv-icon-suggestion" />
          <span className="conv-msg-label">{msg.content || 'This looks like actionable work'}</span>
        </div>
        <div className="conv-promote-actions">
          <button className="conv-btn conv-btn-apply" onClick={() => onPromote?.(msg)}>
            <Check size={14} /> Create directive
          </button>
          <button className="conv-btn conv-btn-dismiss" onClick={() => onDismiss?.(msg)}>
            Not now
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Render a single full-card status message (non-compact types)
// ---------------------------------------------------------------------------

function renderCardStatus(msg, props) {
  switch (msg.type) {
    case MSG_TYPES.GOAL_PROCESSING:
      return <GoalProcessingMessage key={msg.id} msg={msg} onRetry={props.onRetry} />
    case MSG_TYPES.GOAL_COMPLETE:
      return <GoalCompleteMessage key={msg.id} msg={msg} />
    case MSG_TYPES.DIRECTIVE_PREVIEW:
      return (
        <DirectivePreviewMessage
          key={msg.id}
          msg={msg}
          onApply={props.onApply}
          onReject={props.onReject}
          applying={props.applying}
          isPending={props.pendingDirective?.directive_id === msg.directive?.directive_id}
        />
      )
    case MSG_TYPES.ATTENTION:
      return <AttentionMessage key={msg.id} msg={msg} />
    case MSG_TYPES.PROMOTE_SUGGESTION:
      return <PromoteSuggestionMessage key={msg.id} msg={msg} onPromote={props.onPromoteToDirective} onDismiss={props.onDismissPromotion} />
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Timeline with grouped status messages
// ---------------------------------------------------------------------------

/**
 * Groups consecutive status messages into clusters. Chat messages (user,
 * assistant) always stand alone. A status group may contain a mix of compact
 * one-liners and full-card statuses — the compact ones render as a tight
 * stack of inline indicators, while cards keep their current appearance but
 * with reduced surrounding spacing.
 */
function groupMessages(messages) {
  const groups = []
  let currentStatusGroup = null

  for (const msg of messages) {
    if (CHAT_TYPES.has(msg.type)) {
      // Flush any pending status group
      if (currentStatusGroup) {
        groups.push({ type: 'status', messages: currentStatusGroup })
        currentStatusGroup = null
      }
      groups.push({ type: 'chat', msg })
    } else {
      // Status message — accumulate into group
      if (!currentStatusGroup) currentStatusGroup = []
      currentStatusGroup.push(msg)
    }
  }

  // Flush trailing status group
  if (currentStatusGroup) {
    groups.push({ type: 'status', messages: currentStatusGroup })
  }

  return groups
}

/**
 * Builds a short summary label for the collapsed status group header.
 * Shows the most recent/important status, plus a count if there are more.
 */
function buildGroupSummary(messages) {
  // Pick the most "interesting" message for the summary label
  const priority = [
    MSG_TYPES.GOAL_PROCESSING, MSG_TYPES.GOAL_COMPLETE,
    MSG_TYPES.DIRECTIVE_PREVIEW, MSG_TYPES.GOAL_CREATED,
    MSG_TYPES.DIRECTIVE_APPLIED, MSG_TYPES.ATTENTION,
    MSG_TYPES.ERROR, MSG_TYPES.THINKING,
  ]

  // Use the last message as default, but prefer higher-priority types
  let best = messages[messages.length - 1]
  let bestRank = priority.indexOf(best.type)
  for (const msg of messages) {
    const rank = priority.indexOf(msg.type)
    if (rank !== -1 && (bestRank === -1 || rank < bestRank)) {
      best = msg
      bestRank = rank
    }
  }

  const labels = {
    [MSG_TYPES.THINKING]: 'Processing...',
    [MSG_TYPES.GOAL_CREATED]: 'New work created',
    [MSG_TYPES.GOAL_PROCESSING]: 'Processing work...',
    [MSG_TYPES.GOAL_COMPLETE]: 'Work complete',
    [MSG_TYPES.DIRECTIVE_PREVIEW]: 'Directive ready',
    [MSG_TYPES.DIRECTIVE_APPLIED]: 'Changes applied',
    [MSG_TYPES.DIRECTIVE_REJECTED]: 'Changes rejected',
    [MSG_TYPES.ERROR]: 'Error',
    [MSG_TYPES.ATTENTION]: 'Attention',
    [MSG_TYPES.SYSTEM]: best.content?.slice(0, 40) || 'System',
    [MSG_TYPES.PROMOTE_SUGGESTION]: 'Suggestion',
  }

  const label = labels[best.type] || 'Activity'
  const icon = {
    [MSG_TYPES.THINKING]: <Loader size={11} className="conv-spinner" />,
    [MSG_TYPES.GOAL_CREATED]: <Sparkles size={11} className="conv-icon-goal" />,
    [MSG_TYPES.GOAL_PROCESSING]: <Loader size={11} className="conv-spinner" />,
    [MSG_TYPES.GOAL_COMPLETE]: <Check size={11} className="conv-icon-success" />,
    [MSG_TYPES.DIRECTIVE_PREVIEW]: <Target size={11} className="conv-icon-directive" />,
    [MSG_TYPES.DIRECTIVE_APPLIED]: <Check size={11} className="conv-icon-success" />,
    [MSG_TYPES.DIRECTIVE_REJECTED]: <X size={11} className="conv-icon-rejected" />,
    [MSG_TYPES.ERROR]: <AlertCircle size={11} className="conv-icon-error" />,
    [MSG_TYPES.ATTENTION]: <AlertCircle size={11} className="conv-icon-attention" />,
  }

  return { label, icon: icon[best.type] || null, count: messages.length }
}

function StatusGroup({ messages, props }) {
  // Default open so notifications are always visible; users can collapse.
  const [expanded, setExpanded] = useState(true)
  const toggle = useCallback(() => setExpanded(v => !v), [])

  const { label, icon, count } = buildGroupSummary(messages)

  return (
    <div className={`conv-status-box${expanded ? ' expanded' : ''}`}>
      <button className="conv-status-box-header" onClick={toggle}>
        <span className="conv-status-box-icon">{icon}</span>
        <span className="conv-status-box-label">{label}</span>
        {count > 1 && <span className="conv-status-box-count">{count}</span>}
        <ChevronDown size={12} className={`conv-status-box-chevron${expanded ? ' open' : ''}`} />
      </button>
      {expanded && (
        <div className="conv-status-box-body">
          {messages.map((msg) => {
            if (COMPACT_TYPES.has(msg.type)) {
              return renderCompactStatus(msg)
            }
            return renderCardStatus(msg, props)
          })}
        </div>
      )}
    </div>
  )
}

function ConversationTimeline({ messages, currentUserId, pendingDirective, applying, onApply, onReject, onRetry, onPromoteToDirective, onDismissPromotion }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!messages || messages.length === 0) return null

  const groups = groupMessages(messages)
  const cardProps = { pendingDirective, applying, onApply, onReject, onRetry, onPromoteToDirective, onDismissPromotion }

  return (
    <div className="conv-timeline">
      {groups.map((group, i) => {
        if (group.type === 'chat') {
          const msg = group.msg
          if (msg.type === MSG_TYPES.USER) {
            return <UserMessage key={msg.id} msg={msg} currentUserId={currentUserId} onPromoteToDirective={onPromoteToDirective} />
          }
          return <AssistantMessage key={msg.id} msg={msg} />
        }
        // Status group
        return <StatusGroup key={`sg-${i}`} messages={group.messages} props={cardProps} />
      })}
      <div ref={bottomRef} />
    </div>
  )
}

export default ConversationTimeline
