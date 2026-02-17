import { AlertTriangle, CheckCircle, Clock, TrendingUp, TrendingDown, Minus, Zap } from 'lucide-react'
import './GoalProgressBar.css'

const VELOCITY_ICONS = {
  accelerating: TrendingUp,
  steady: Minus,
  stalling: TrendingDown,
}

const VELOCITY_LABELS = {
  accelerating: 'Accelerating',
  steady: 'Steady',
  stalling: 'Stalling',
}

function SegmentedBar({ segments, total }) {
  if (total === 0) return null

  return (
    <div className="goal-progress-segmented-bar">
      {segments.map(({ count, className }) => {
        if (count === 0) return null
        const pct = (count / total) * 100
        return (
          <div
            key={className}
            className={`goal-progress-segment ${className}`}
            style={{ width: `${pct}%` }}
            title={`${count} ${className.replace('segment-', '')}`}
          />
        )
      })}
    </div>
  )
}

function GoalProgressBar({ progress, compact = false }) {
  if (!progress || progress.total_issues === 0) {
    return null
  }

  const {
    total_issues,
    done_count,
    in_progress_count,
    blocked_count,
    failed_count,
    completion_percent,
    characterized_count,
    characterization_percent,
    velocity_7d,
    velocity_trend,
  } = progress

  const segments = [
    { count: done_count, className: 'segment-done' },
    { count: in_progress_count, className: 'segment-in-progress' },
    { count: blocked_count, className: 'segment-blocked' },
    { count: failed_count, className: 'segment-failed' },
  ]

  const VelocityIcon = VELOCITY_ICONS[velocity_trend] || Minus

  if (compact) {
    return (
      <div className="goal-progress-compact">
        <SegmentedBar segments={segments} total={total_issues} />
        <div className="goal-progress-compact-stats">
          <span className="goal-progress-pct">{Math.round(completion_percent)}%</span>
          {blocked_count > 0 && (
            <span className="goal-progress-blocked-badge" title={`${blocked_count} blocked`}>
              <AlertTriangle size={10} />
              {blocked_count}
            </span>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="goal-progress-full">
      <div className="goal-progress-header">
        <span className="goal-progress-title">Progress</span>
        <span className="goal-progress-pct">{Math.round(completion_percent)}%</span>
      </div>

      <SegmentedBar segments={segments} total={total_issues} />

      <div className="goal-progress-details">
        <div className="goal-progress-stat" title="Completed">
          <CheckCircle size={12} className="stat-icon stat-done" />
          <span>{done_count}/{total_issues}</span>
        </div>

        {blocked_count > 0 && (
          <div className="goal-progress-stat goal-progress-stat-warn" title="Blocked">
            <AlertTriangle size={12} className="stat-icon stat-blocked" />
            <span>{blocked_count} blocked</span>
          </div>
        )}

        {failed_count > 0 && (
          <div className="goal-progress-stat goal-progress-stat-error" title="Failed">
            <AlertTriangle size={12} className="stat-icon stat-failed" />
            <span>{failed_count} failed</span>
          </div>
        )}

        <div className="goal-progress-stat" title={`Characterized: ${characterized_count}/${total_issues}`}>
          <Zap size={12} className="stat-icon stat-char" />
          <span>{Math.round(characterization_percent)}% characterized</span>
        </div>

        <div className="goal-progress-stat" title={`${velocity_7d} completed this week (${VELOCITY_LABELS[velocity_trend]})`}>
          <VelocityIcon size={12} className={`stat-icon stat-velocity-${velocity_trend}`} />
          <span>{velocity_7d}/wk</span>
        </div>
      </div>
    </div>
  )
}

export default GoalProgressBar
