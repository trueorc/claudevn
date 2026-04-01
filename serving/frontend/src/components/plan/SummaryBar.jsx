import { Activity, Clock, AlertCircle, Target, Layers, XCircle, CheckCircle2, GitMerge } from 'lucide-react'
import './Plan.css'

function SummaryBar({ data, loading }) {
  if (loading && !data) {
    return (
      <div className="plan-summary-bar plan-summary-bar--loading">
        <span className="plan-summary-loading-text">Loading plan summary...</span>
      </div>
    )
  }

  if (!data) return null

  const {
    in_progress_count = 0,
    merging_count = 0,
    ready_count = 0,
    blocked_count = 0,
    backlog_count = 0,
    failed_count = 0,
    done_count = 0,
    total_count = 0,
    focus_summary,
  } = data

  // Derive a short focus label from the full optimization_target
  const focusLabel = focus_summary && !focus_summary.includes('unavailable')
    ? focus_summary
    : null

  const progressPct = total_count > 0 ? Math.round((done_count / total_count) * 100) : 0

  return (
    <div className="plan-summary-bar-wrapper">
      <div className="plan-summary-bar">
        <div className="plan-summary-stats">
          {done_count > 0 && (
            <>
              <div className="plan-stat plan-stat--done">
                <CheckCircle2 size={14} />
                <span className="plan-stat-value">{done_count}</span>
                <span className="plan-stat-label">done</span>
              </div>
              <span className="plan-stat-separator" />
            </>
          )}
          <div className="plan-stat plan-stat--active">
            <Activity size={14} />
            <span className="plan-stat-value">{in_progress_count}</span>
            <span className="plan-stat-label">active</span>
          </div>
          <span className="plan-stat-separator" />
          {merging_count > 0 && (
            <>
              <div className="plan-stat plan-stat--merging">
                <GitMerge size={14} />
                <span className="plan-stat-value">{merging_count}</span>
                <span className="plan-stat-label">merging</span>
              </div>
              <span className="plan-stat-separator" />
            </>
          )}
          <div className="plan-stat plan-stat--queued">
            <Clock size={14} />
            <span className="plan-stat-value">{ready_count}</span>
            <span className="plan-stat-label">queued</span>
          </div>
          <span className="plan-stat-separator" />
          <div className="plan-stat plan-stat--blocked">
            <AlertCircle size={14} />
            <span className="plan-stat-value">{blocked_count}</span>
            <span className="plan-stat-label">blocked</span>
          </div>
          {backlog_count > 0 && (
            <>
              <span className="plan-stat-separator" />
              <div className="plan-stat plan-stat--backlog">
                <Layers size={14} />
                <span className="plan-stat-value">{backlog_count}</span>
                <span className="plan-stat-label">backlog</span>
              </div>
            </>
          )}
          {failed_count > 0 && (
            <>
              <span className="plan-stat-separator" />
              <div className="plan-stat plan-stat--failed">
                <XCircle size={14} />
                <span className="plan-stat-value">{failed_count}</span>
                <span className="plan-stat-label">failed</span>
              </div>
            </>
          )}
        </div>
        {focusLabel && (
          <div className="plan-summary-focus">
            <Target size={14} />
            <span className="plan-summary-focus-text">{focusLabel}</span>
          </div>
        )}
      </div>
      {total_count > 0 && (
        <div className="plan-progress">
          <div className="plan-progress-bar">
            <div className="plan-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <span className="plan-progress-label">{done_count} of {total_count} completed ({progressPct}%)</span>
        </div>
      )}
    </div>
  )
}

export default SummaryBar
