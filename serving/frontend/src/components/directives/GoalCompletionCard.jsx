import { Check } from 'lucide-react'

const STAGE_LABELS = {
  queued: 'Queuing work',
  decomposing: 'Decomposing goal',
  characterizing: 'Characterizing work items',
  creating_issues: 'Creating backlog items',
}

const STAGE_ORDER = ['queued', 'decomposing', 'characterizing', 'creating_issues']

function formatDuration(startedAt, completedAt) {
  if (!startedAt) return null
  const start = new Date(startedAt).getTime()
  const end = completedAt ? new Date(completedAt).getTime() : Date.now()
  const secs = Math.floor((end - start) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

/**
 * Reusable completion card showing the stepper in finished state
 * with optional issues list and reasoning.
 *
 * Props:
 *   issues     - Array of { issue_id, title, priority }
 *   reasoning  - Optional string from decomposition
 *   startedAt  - ISO string for elapsed time calculation
 *   completedAt - ISO string (optional, defaults to now for live cards)
 */
export default function GoalCompletionCard({ issues = [], reasoning, startedAt, completedAt }) {
  const duration = formatDuration(startedAt, completedAt)

  return (
    <div className="conv-msg conv-msg-system">
      <div className="conv-msg-bubble conv-bubble-system conv-processing-card conv-processing-complete">
        <div className="conv-processing-header">
          <Check size={14} className="conv-icon-success" />
          <span className="conv-processing-label">Complete</span>
          {duration && <span className="conv-elapsed">{duration}</span>}
        </div>
        <div className="conv-stage-stepper">
          {STAGE_ORDER.map((stage) => (
            <div key={stage} className="conv-stage-step done">
              <div className="conv-stage-dot">
                <Check size={10} />
              </div>
              <span className="conv-stage-name">{STAGE_LABELS[stage]}</span>
            </div>
          ))}
        </div>
        {issues.length > 0 && (
          <p className="conv-issues-summary">{issues.length} issue{issues.length !== 1 ? 's' : ''} created</p>
        )}
        {reasoning && (
          <p className="conv-reasoning">{reasoning}</p>
        )}
      </div>
    </div>
  )
}
