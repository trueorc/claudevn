import { useState } from 'react'
import { Container, CheckCircle2, Clock, AlertTriangle, ChevronDown, ChevronRight, Eye, Package } from 'lucide-react'
import './ComputeEnvironmentPanel.css'

const STATUS_CONFIG = {
  proposed: { icon: Clock, label: 'Proposed — Awaiting Review', className: 'cep-status--proposed' },
  approved: { icon: CheckCircle2, label: 'Approved — Ready to Build', className: 'cep-status--approved' },
  building: { icon: Clock, label: 'Building Image...', className: 'cep-status--building' },
  ready: { icon: CheckCircle2, label: 'Ready', className: 'cep-status--ready' },
  active: { icon: CheckCircle2, label: 'Active — Running', className: 'cep-status--active' },
  failed: { icon: AlertTriangle, label: 'Build Failed', className: 'cep-status--failed' },
}

function RequirementRow({ req }) {
  return (
    <div className="cep-req">
      <Package size={12} className="cep-req-icon" />
      <span className="cep-req-name">{req.name}</span>
      {req.version && <span className="cep-req-version">{req.version}</span>}
      <span className="cep-req-reason">{req.reason}</span>
    </div>
  )
}

/**
 * Compute environment panel — first-class artifact of planning.
 * Shows detected requirements, generated Dockerfile, and approval controls.
 */
export default function ComputeEnvironmentPanel({ environment, onApprove, approving = false }) {
  const [showDockerfile, setShowDockerfile] = useState(false)

  if (!environment) return null

  const statusInfo = STATUS_CONFIG[environment.status] || STATUS_CONFIG.proposed
  const StatusIcon = statusInfo.icon
  const isProposed = environment.status === 'proposed'

  return (
    <div className={`cep-panel ${isProposed ? 'cep-panel--needs-action' : ''}`}>
      <div className="cep-header">
        <Container size={16} className="cep-header-icon" />
        <span className="cep-title">Compute Environment</span>
        <span className={`cep-status ${statusInfo.className}`}>
          <StatusIcon size={12} />
          {statusInfo.label}
        </span>
      </div>

      {/* Base image */}
      <div className="cep-base">
        <span className="cep-base-label">Base:</span>
        <span className="cep-base-image">{environment.base_image}</span>
        <span className="cep-base-units">{environment.work_unit_ids?.length || 0} work units</span>
      </div>

      {/* Requirements */}
      {environment.requirements?.length > 0 && (
        <div className="cep-requirements">
          <span className="cep-section-label">Detected Requirements</span>
          <div className="cep-req-list">
            {environment.requirements.map((req, i) => (
              <RequirementRow key={i} req={req} />
            ))}
          </div>
        </div>
      )}

      {/* Dockerfile preview */}
      {environment.dockerfile_content && (
        <div className="cep-dockerfile">
          <button className="cep-dockerfile-toggle" onClick={() => setShowDockerfile(!showDockerfile)}>
            <Eye size={12} />
            {showDockerfile ? 'Hide' : 'View'} Dockerfile
            {showDockerfile ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
          {showDockerfile && (
            <pre className="cep-dockerfile-content">{environment.dockerfile_content}</pre>
          )}
        </div>
      )}

      {/* Image tag if built */}
      {environment.image_tag && (
        <div className="cep-image-info">
          <span className="cep-image-label">Image:</span>
          <span className="cep-image-tag">{environment.image_tag}</span>
        </div>
      )}

      {/* Approval action */}
      {isProposed && onApprove && (
        <div className="cep-actions">
          <button
            className="cep-approve-btn"
            onClick={onApprove}
            disabled={approving}
          >
            <CheckCircle2 size={14} />
            {approving ? 'Approving...' : 'Approve Environment'}
          </button>
        </div>
      )}
    </div>
  )
}
