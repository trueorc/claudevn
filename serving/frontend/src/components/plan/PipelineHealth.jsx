import { GitBranch, Play, ShieldCheck, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import './PipelineHealth.css'

const LAYER_CONFIG = {
  decomposition: { icon: GitBranch, label: 'Decomposition', layer: 'L1' },
  dispatch: { icon: Play, label: 'Dispatch', layer: 'L2' },
  verification: { icon: ShieldCheck, label: 'Verification', layer: 'L3' },
}

const STATUS_ICONS = {
  healthy: CheckCircle2,
  degraded: AlertTriangle,
  failed: XCircle,
  idle: CheckCircle2,
}

/**
 * Per-layer pipeline health indicators.
 * Shows whether each layer of the system is functioning.
 */
export default function PipelineHealth({ layers = {} }) {
  return (
    <div className="ph-container">
      {Object.entries(LAYER_CONFIG).map(([key, config]) => {
        const status = layers[key] || { status: 'idle', detail: 'No activity' }
        const LayerIcon = config.icon
        const StatusIcon = STATUS_ICONS[status.status] || CheckCircle2

        return (
          <div key={key} className={`ph-layer ph-layer--${status.status}`}>
            <div className="ph-layer-header">
              <LayerIcon size={14} />
              <span className="ph-layer-label">{config.label}</span>
              <span className="ph-layer-tag">{config.layer}</span>
            </div>
            <div className="ph-layer-status">
              <StatusIcon size={12} />
              <span className="ph-layer-status-text">{status.status}</span>
            </div>
            {status.detail && (
              <p className="ph-layer-detail">{status.detail}</p>
            )}
            {status.active_count != null && (
              <span className="ph-layer-count">{status.active_count} active</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
