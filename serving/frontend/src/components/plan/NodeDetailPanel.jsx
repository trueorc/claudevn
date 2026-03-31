import { X, Clock, GitBranch, Target, FileCode, Shield } from 'lucide-react'
import './NodeDetailPanel.css'

/**
 * Detail panel shown when a graph node is clicked.
 * Overlays the right side of the graph area.
 */
export default function NodeDetailPanel({ node, onClose }) {
  if (!node) return null

  const colors = {
    draft: 'var(--text-muted)',
    ready: 'var(--primary)',
    queued: '#3b82f6',
    executing: '#3b82f6',
    completed: 'var(--status-online)',
    verified: 'var(--status-online)',
    failed: 'var(--status-offline)',
    failed_verification: 'var(--status-offline)',
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
