/**
 * EvaluationStatusIndicator - Visual status indicator for goal comment evaluation state.
 *
 * Displays a compact visual indicator showing the evaluation status of a goal comment:
 * - not_evaluated: Gray dot (comment submitted but not yet processed)
 * - pending: Red/yellow dot (has unevaluated items needing attention)
 * - evaluating: Amber pulsing dot (currently being evaluated)
 * - evaluated: Green checkmark (evaluation complete)
 * - failed: Red dot with error state (evaluation failed)
 *
 * Designed for inline display with proper accessibility support.
 */

import './EvaluationStatusIndicator.css'

// Status configuration for visual styling
const STATUS_CONFIG = {
  not_evaluated: {
    color: 'var(--text-muted)',
    label: 'Not yet evaluated',
    icon: 'dot'
  },
  pending: {
    color: 'var(--warning, #f59e0b)',
    label: 'Pending evaluation',
    icon: 'dot'
  },
  evaluating: {
    color: 'var(--status-degraded)',
    label: 'Evaluation in progress',
    icon: 'dot',
    animated: true
  },
  evaluated: {
    color: 'var(--status-online)',
    label: 'Evaluation complete',
    icon: 'check'
  },
  failed: {
    color: 'var(--status-offline)',
    label: 'Evaluation failed',
    icon: 'error'
  }
}

// Fallback for unknown statuses
const DEFAULT_CONFIG = STATUS_CONFIG.not_evaluated

function EvaluationStatusIndicator({ status, size = 'small', showLabel = false }) {
  const config = STATUS_CONFIG[status] || DEFAULT_CONFIG
  const isAnimated = config.animated === true

  // Size classes for different contexts
  const sizeClass = size === 'large' ? 'evaluation-status-lg' : 'evaluation-status-sm'

  return (
    <span
      className={`evaluation-status-indicator ${sizeClass} ${isAnimated ? 'animated' : ''}`}
      role="status"
      aria-label={config.label}
    >
      <span
        className={`evaluation-status-dot ${config.icon}`}
        style={{ '--status-color': config.color }}
        aria-hidden="true"
      >
        {config.icon === 'check' && (
          <svg
            viewBox="0 0 12 12"
            fill="none"
            className="evaluation-status-check-icon"
            aria-hidden="true"
          >
            <path
              d="M2.5 6L5 8.5L9.5 3.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
        {config.icon === 'error' && (
          <svg
            viewBox="0 0 12 12"
            fill="none"
            className="evaluation-status-error-icon"
            aria-hidden="true"
          >
            <path
              d="M3.5 3.5L8.5 8.5M8.5 3.5L3.5 8.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        )}
      </span>
      {showLabel && (
        <span className="evaluation-status-label">{config.label}</span>
      )}
    </span>
  )
}

export { STATUS_CONFIG }
export default EvaluationStatusIndicator
