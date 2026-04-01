import { ArrowLeft, RefreshCw, Scissors, CheckCircle2, RotateCcw } from 'lucide-react'
import './DirectiveActionBar.css'

/**
 * Sticky action bar at top of directive detail view.
 * Shows contextual actions based on goal state:
 * - Failed: Retry button
 * - Has work units: Refine button
 * - Has draft units: Approve button
 */
export default function DirectiveActionBar({
  goal,
  hasDraftUnits,
  hasWorkUnits,
  onBack,
  onApprove,
  onRefine,
  onRefresh,
  onRetry,
  approving,
  recomposing,
  retrying,
}) {
  const title = goal?.title || goal?.description?.slice(0, 80) || 'Directive'
  const isFailed = goal?.status === 'failed'

  return (
    <div className="dab">
      <button className="dab-back" onClick={onBack} title="Back to project overview">
        <ArrowLeft size={16} />
        <span>Overview</span>
      </button>

      <span className="dab-title">{title}</span>

      <div className="dab-actions">
        <button className="dab-btn dab-btn--secondary" onClick={onRefresh} title="Refresh">
          <RefreshCw size={14} />
        </button>

        {isFailed && onRetry && (
          <button
            className="dab-btn dab-btn--retry"
            onClick={onRetry}
            disabled={retrying}
            title="Retry decomposition"
          >
            <RotateCcw size={14} />
            {retrying ? 'Retrying...' : 'Retry'}
          </button>
        )}

        {hasWorkUnits && !isFailed && (
          <button
            className="dab-btn dab-btn--secondary"
            onClick={onRefine}
            disabled={recomposing}
            title="Refine decomposition"
          >
            <Scissors size={14} />
            {recomposing ? 'Refining...' : 'Refine'}
          </button>
        )}

        {hasDraftUnits && (
          <button
            className="dab-btn dab-btn--approve"
            onClick={onApprove}
            disabled={approving}
          >
            <CheckCircle2 size={14} />
            {approving ? 'Approving...' : 'Approve Decomposition'}
          </button>
        )}
      </div>
    </div>
  )
}
