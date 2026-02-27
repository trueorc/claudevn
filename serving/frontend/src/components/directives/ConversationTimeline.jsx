import { useRef, useEffect, useState } from 'react'
import { Loader, Check, X, AlertCircle, ArrowRight, Sparkles, Target, FileText, Clock, RefreshCw } from 'lucide-react'
import { MSG_TYPES } from '../../hooks/useConversation'
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

function UserMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-user">
      <div className="conv-msg-bubble conv-bubble-user">
        <p className="conv-msg-text">{msg.content}</p>
        <span className="conv-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function ThinkingMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-thinking">
        <Loader size={14} className="conv-spinner" />
        <span>{msg.content}</span>
      </div>
    </div>
  )
}

function GoalCreatedMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system">
        <div className="conv-msg-header">
          <Sparkles size={14} className="conv-icon-goal" />
          <span className="conv-msg-label">New Work Created</span>
        </div>
      </div>
    </div>
  )
}

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

function DirectiveAppliedMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-applied">
        <div className="conv-msg-header">
          <Check size={14} className="conv-icon-success" />
          <span className="conv-msg-label">Changes Applied</span>
          {msg.directive?.interpretation?.detected_intent && (
            <span className={`conv-intent-badge intent-${msg.directive.interpretation.detected_intent}`}>
              {msg.directive.interpretation.detected_intent}
            </span>
          )}
        </div>
        {msg.directive?.interpretation?.summary && (
          <p className="conv-directive-summary">{msg.directive.interpretation.summary}</p>
        )}
      </div>
    </div>
  )
}

function DirectiveRejectedMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-rejected">
        <div className="conv-msg-header">
          <X size={14} className="conv-icon-rejected" />
          <span className="conv-msg-label">Changes Rejected</span>
        </div>
      </div>
    </div>
  )
}

function ErrorMessage({ msg }) {
  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-error">
        <AlertCircle size={14} className="conv-icon-error" />
        <span>{msg.content}</span>
      </div>
    </div>
  )
}

function ConversationTimeline({ messages, pendingDirective, applying, onApply, onReject, onRetry }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!messages || messages.length === 0) return null

  return (
    <div className="conv-timeline">
      {messages.map((msg) => {
        switch (msg.type) {
          case MSG_TYPES.USER:
            return <UserMessage key={msg.id} msg={msg} />
          case MSG_TYPES.THINKING:
            return <ThinkingMessage key={msg.id} msg={msg} />
          case MSG_TYPES.GOAL_CREATED:
            return <GoalCreatedMessage key={msg.id} msg={msg} />
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
          case MSG_TYPES.DIRECTIVE_APPLIED:
            return <DirectiveAppliedMessage key={msg.id} msg={msg} />
          case MSG_TYPES.DIRECTIVE_REJECTED:
            return <DirectiveRejectedMessage key={msg.id} msg={msg} />
          case MSG_TYPES.ERROR:
            return <ErrorMessage key={msg.id} msg={msg} />
          default:
            return null
        }
      })}
      <div ref={bottomRef} />
    </div>
  )
}

export default ConversationTimeline
