import { useNavigate } from 'react-router-dom'
import { ShieldCheck, ChevronRight, AlertTriangle, CheckCircle2, XCircle, Clock } from 'lucide-react'
import './VerificationPanel.css'

const RESULT_CONFIG = {
  passed: { icon: CheckCircle2, label: 'Passed', className: 'vp-result--passed' },
  failed: { icon: XCircle, label: 'Failed', className: 'vp-result--failed' },
  pending: { icon: Clock, label: 'Pending', className: 'vp-result--pending' },
  needs_human_review: { icon: AlertTriangle, label: 'Review', className: 'vp-result--review' },
}

function VerificationItem({ result }) {
  const navigate = useNavigate()
  const config = RESULT_CONFIG[result.status] || RESULT_CONFIG.pending
  const StatusIcon = config.icon

  return (
    <button
      className="vp-item"
      onClick={() => navigate(`/verify?unit=${result.work_unit_id}`)}
    >
      <div className="vp-item-header">
        <span className={`vp-result ${config.className}`}>
          <StatusIcon size={12} />
          {config.label}
        </span>
        <span className="vp-item-id">{result.work_unit_id}</span>
        <ChevronRight size={14} className="vp-item-chevron" />
      </div>
      {result.details && (
        <p className="vp-item-details">{result.details}</p>
      )}
    </button>
  )
}

/**
 * Layer 3 panel — shows recent verification results and integration status.
 * Highlights failures needing attention.
 */
export default function VerificationPanel({ results = [] }) {
  const navigate = useNavigate()

  const failures = results.filter(r => r.status === 'failed' || r.status === 'needs_human_review')
  const passed = results.filter(r => r.status === 'passed')
  const pending = results.filter(r => r.status === 'pending')

  return (
    <div className="vp-panel">
      <div className="vp-panel-header">
        <span className="vp-panel-title">Verification</span>
        {failures.length > 0 && (
          <span className="vp-panel-badge vp-panel-badge--alert">{failures.length}</span>
        )}
      </div>

      {/* Summary strip */}
      <div className="vp-summary">
        <span className="vp-summary-item vp-summary--passed">
          <CheckCircle2 size={12} /> {passed.length}
        </span>
        <span className="vp-summary-item vp-summary--failed">
          <XCircle size={12} /> {failures.length}
        </span>
        <span className="vp-summary-item vp-summary--pending">
          <Clock size={12} /> {pending.length}
        </span>
      </div>

      {/* Show failures first */}
      {failures.length > 0 ? (
        <div className="vp-list">
          {failures.slice(0, 5).map((result) => (
            <VerificationItem key={result.work_unit_id} result={result} />
          ))}
        </div>
      ) : results.length === 0 ? (
        <p className="vp-empty">No verification results yet</p>
      ) : (
        <p className="vp-empty vp-all-clear">All checks passing</p>
      )}

      <button className="vp-view-all" onClick={() => navigate('/verify')}>
        View verification details
        <ChevronRight size={14} />
      </button>
    </div>
  )
}
