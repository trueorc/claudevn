import { useRef, useEffect, useState } from 'react'
import { Loader, Check, X, AlertCircle, ArrowRight, Sparkles, Target, FileText, Clock, RefreshCw, Bot, ChevronRight } from 'lucide-react'
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

/** Message types that render as compact single-line indicators. */
const COMPACT_TYPES = new Set([
  MSG_TYPES.THINKING,
  MSG_TYPES.GOAL_CREATED,
  MSG_TYPES.DIRECTIVE_APPLIED,
  MSG_TYPES.DIRECTIVE_REJECTED,
  MSG_TYPES.SYSTEM,
  MSG_TYPES.ERROR,
])

// ---------------------------------------------------------------------------
// Chat message components
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
// Compact single-line status indicators
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

// ---------------------------------------------------------------------------
// Full card status components (interactive / multi-line)
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
            The current stage has not progressed for 5 minutes. The operation may still be running on the server.
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
  const issues = result?.issues_created || result?.created_issues || result?.issues || []

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
// Render a compact status line for simple status messages
// ---------------------------------------------------------------------------

function renderCompactMessage(msg) {
  const time = formatTime(msg.timestamp)

  switch (msg.type) {
    case MSG_TYPES.THINKING:
      return (
        <CompactStatusLine
          icon={<Loader size={11} className="conv-spinner" />}
          label={msg.content || 'Thinking...'}
          className="conv-status-thinking"
          time={time}
        />
      )
    case MSG_TYPES.GOAL_CREATED:
      return (
        <CompactStatusLine
          icon={<Sparkles size={11} className="conv-icon-goal" />}
          label="New work created"
          className="conv-status-goal"
          time={time}
        />
      )
    case MSG_TYPES.DIRECTIVE_APPLIED: {
      const summary = msg.directive?.interpretation?.summary
      return (
        <CompactStatusLine
          icon={<Check size={11} className="conv-icon-success" />}
          label={summary ? `Applied — ${summary}` : 'Changes applied'}
          className="conv-status-applied"
          time={time}
        />
      )
    }
    case MSG_TYPES.DIRECTIVE_REJECTED:
      return (
        <CompactStatusLine
          icon={<X size={11} className="conv-icon-rejected" />}
          label="Changes rejected"
          className="conv-status-rejected"
          time={time}
        />
      )
    case MSG_TYPES.ERROR:
      return (
        <CompactStatusLine
          icon={<AlertCircle size={11} className="conv-icon-error" />}
          label={msg.content || 'Error'}
          className="conv-status-error"
          time={time}
        />
      )
    case MSG_TYPES.SYSTEM: {
      const parts = (msg.content || '').split(/\*\*(.*?)\*\*/g)
      return (
        <div className="conv-status-line conv-status-system">
          <span className="conv-status-label">
            {parts.map((part, i) => i % 2 === 1 ? <strong key={i}>{part}</strong> : part)}
          </span>
          <span className="conv-status-time">{time}</span>
        </div>
      )
    }
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Collapsible box that wraps consecutive compact status messages
// ---------------------------------------------------------------------------

function StatusGroup({ msgs }) {
  const [expanded, setExpanded] = useState(true)
  const count = msgs.length

  if (count === 1) {
    return <div className="conv-status-group-single">{renderCompactMessage(msgs[0])}</div>
  }

  return (
    <div className="conv-status-group">
      <button
        className="conv-status-group-toggle"
        onClick={() => setExpanded(prev => !prev)}
      >
        <ChevronRight size={12} className={`conv-status-chevron ${expanded ? 'open' : ''}`} />
        <span className="conv-status-group-summary">
          {count} status update{count !== 1 ? 's' : ''}
        </span>
      </button>
      {expanded && (
        <div className="conv-status-group-items">
          {msgs.map(m => <div key={m.id}>{renderCompactMessage(m)}</div>)}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Group consecutive compact messages, interleave with full-card messages
// ---------------------------------------------------------------------------

const MAX_STATUS_PER_GROUP = 20

function buildRenderGroups(messages) {
  const groups = []
  let compactBuf = []

  const flushCompact = () => {
    // Split into chunks of MAX_STATUS_PER_GROUP
    while (compactBuf.length > 0) {
      groups.push({ kind: 'compact', msgs: compactBuf.splice(0, MAX_STATUS_PER_GROUP) })
    }
  }

  for (const msg of messages) {
    if (COMPACT_TYPES.has(msg.type)) {
      compactBuf.push(msg)
    } else {
      flushCompact()
      groups.push({ kind: 'full', msg })
    }
  }
  flushCompact()
  return groups
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

function ConversationTimeline({ messages, currentUserId, pendingDirective, applying, onApply, onReject, onRetry, onPromoteToDirective, onDismissPromotion }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!messages || messages.length === 0) return null

  const groups = buildRenderGroups(messages)

  return (
    <div className="conv-timeline">
      {groups.map((group, gi) => {
        if (group.kind === 'compact') {
          return <StatusGroup key={`sg-${group.msgs[0].id}`} msgs={group.msgs} />
        }

        const msg = group.msg
        switch (msg.type) {
          case MSG_TYPES.USER:
            return <UserMessage key={msg.id} msg={msg} currentUserId={currentUserId} onPromoteToDirective={onPromoteToDirective} />
          case MSG_TYPES.ASSISTANT:
            return <AssistantMessage key={msg.id} msg={msg} />
          case MSG_TYPES.GOAL_PROCESSING:
            return <GoalProcessingMessage key={msg.id} msg={msg} onRetry={onRetry} />
          case MSG_TYPES.GOAL_COMPLETE:
            return <GoalCompleteMessage key={msg.id} msg={msg} />
          case MSG_TYPES.DIRECTIVE_PREVIEW:
            return (
              <DirectivePreviewMessage
                key={msg.id}
                msg={msg}
                onApply={onApply}
                onReject={onReject}
                applying={applying}
                isPending={pendingDirective?.directive_id === msg.directive?.directive_id}
              />
            )
          case MSG_TYPES.ATTENTION:
            return <AttentionMessage key={msg.id} msg={msg} />
          case MSG_TYPES.PROMOTE_SUGGESTION:
            return <PromoteSuggestionMessage key={msg.id} msg={msg} onPromote={onPromoteToDirective} onDismiss={onDismissPromotion} />
          default:
            return null
        }
      })}
      <div ref={bottomRef} />
    </div>
  )
}

export default ConversationTimeline
