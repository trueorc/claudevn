import { useState } from 'react'
import { X, Clock, GitBranch, Target, FileCode, Shield, RotateCcw, SkipForward, XCircle } from 'lucide-react'
import { retryUnit, skipUnit, cancelUnit } from '../../api/workUnits'
import './NodeDetailPanel.css'

/**
 * Detail panel shown when a graph node is clicked.
 * Overlays the right side of the graph area.
 */
export default function NodeDetailPanel({ node, onClose, onAction }) {
  if (!node) return null

  const [acting, setActing] = useState(null)
  const [error, setError] = useState(null)

  const colors = {
    draft: 'var(--text-muted)',
    ready: 'var(--primary)',
    queued: '#3b82f6',
    waiting_compute: '#3b82f6',
    executing: '#06b6d4',
    submitted: '#8b5cf6',
    merging: '#a855f7',
    merge_conflict: '#f59e0b',
    completed: 'var(--status-online)',
    verified: 'var(--status-online)',
    failed: 'var(--error)',
    failed_verification: 'var(--error)',
    cancelled: 'var(--text-muted)',
  }

  const isFailed = node.status === 'failed' || node.status === 'failed_verification' || node.status === 'merge_conflict'
  const isActive = ['executing', 'submitted', 'merging', 'verifying', 'queued', 'waiting_compute', 'ready'].includes(node.status)
  const isTerminal = ['completed', 'verified', 'cancelled', 'superseded'].includes(node.status)

  async function handleAction(action) {
    setActing(action)
    setError(null)
    try {
      if (action === 'retry') await retryUnit(node.id)
      else if (action === 'skip') await skipUnit(node.id)
      else if (action === 'cancel') await cancelUnit(node.id)
      if (onAction) onAction(action, node.id)
    } catch (e) {
      setError(e.message || 'Action failed')
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="ndp">
      <div className="ndp-header">
        <div className="ndp-header-left">
          <span className="ndp-status-dot" style={{ background: colors[node.status] || 'var(--text-muted)' }} />
          <span className="ndp-id">{node.id}</span>
        </div>
        <button className="ndp-close" onClick={onClose}><X size={14} /></button>
      </div>

      <p className="ndp-description">{node.description}</p>

      <div className="ndp-meta">
        <span className="ndp-badge">{(node.status || 'draft').toUpperCase()}</span>
        {node.complexity && <span className="ndp-badge">{node.complexity.toUpperCase()}</span>}
      </div>

      {/* Actions for failed units */}
      {isFailed && (
        <div className="ndp-actions">
          <button
            className="ndp-action ndp-action--retry"
            onClick={() => handleAction('retry')}
            disabled={acting !== null}
          >
            <RotateCcw size={12} />
            {acting === 'retry' ? 'Retrying...' : 'Retry'}
          </button>
          <button
            className="ndp-action ndp-action--skip"
            onClick={() => handleAction('skip')}
            disabled={acting !== null}
          >
            <SkipForward size={12} />
            {acting === 'skip' ? 'Skipping...' : 'Skip'}
          </button>
        </div>
      )}

      {/* Cancel for active units */}
      {isActive && !isTerminal && (
        <div className="ndp-actions">
          <button
            className="ndp-action ndp-action--cancel"
            onClick={() => handleAction('cancel')}
            disabled={acting !== null}
          >
            <XCircle size={12} />
            {acting === 'cancel' ? 'Cancelling...' : 'Cancel'}
          </button>
        </div>
      )}

      {error && <div className="ndp-error">{error}</div>}

      {/* Instance / Branch */}
      {node.instance_id && (
        <div className="ndp-row">
          <GitBranch size={12} />
          <span className="ndp-label">Instance:</span>
          <span className="ndp-value">{node.instance_id}</span>
        </div>
      )}

      {/* Timing */}
      {(node.started_at || node.completed_at) && (
        <div className="ndp-section">
          <span className="ndp-section-title"><Clock size={12} /> Timing</span>
          {node.started_at && <div className="ndp-row-sm">Started: {new Date(node.started_at).toLocaleTimeString()}</div>}
          {node.completed_at && <div className="ndp-row-sm">Completed: {new Date(node.completed_at).toLocaleTimeString()}</div>}
        </div>
      )}

      {/* Dependencies */}
      {node.depends_on?.length > 0 && (
        <div className="ndp-section">
          <span className="ndp-section-title"><Shield size={12} /> Depends On</span>
          {node.depends_on.map(dep => (
            <span key={dep} className="ndp-dep">{dep}</span>
          ))}
        </div>
      )}

      {node.depended_by?.length > 0 && (
        <div className="ndp-section">
          <span className="ndp-section-title"><Target size={12} /> Blocks</span>
          {node.depended_by.map(dep => (
            <span key={dep} className="ndp-dep">{dep}</span>
          ))}
        </div>
      )}
    </div>
  )
}
