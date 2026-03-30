import { ArrowLeft, RefreshCw, Scissors, CheckCircle2 } from 'lucide-react'
import './DirectiveActionBar.css'

/**
 * Sticky action bar at top of directive detail view.
 * Prominent Approve button, Refine, Refresh, and Back navigation.
 */
export default function DirectiveActionBar({
  goal,
  hasDraftUnits,
  hasWorkUnits,
  onBack,
  onApprove,
  onRefine,
  onRefresh,
  approving,
  recomposing,
}) {
  const title = goal?.title || goal?.description?.slice(0, 80) || 'Directive'

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

        {hasWorkUnits && (
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
