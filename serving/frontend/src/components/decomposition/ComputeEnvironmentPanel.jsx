import { useState } from 'react'
import { Container, CheckCircle2, Clock, AlertTriangle, ChevronDown, ChevronRight, Eye, Package, Copy, Terminal } from 'lucide-react'
import './ComputeEnvironmentPanel.css'

const STATUS_CONFIG = {
  proposed: { icon: Clock, label: 'Proposed', className: 'cep-status--proposed' },
  approved: { icon: CheckCircle2, label: 'Approved', className: 'cep-status--approved' },
  building: { icon: Clock, label: 'Building', className: 'cep-status--building' },
  ready: { icon: CheckCircle2, label: 'Ready', className: 'cep-status--ready' },
  active: { icon: CheckCircle2, label: 'Active', className: 'cep-status--active' },
  failed: { icon: AlertTriangle, label: 'Failed', className: 'cep-status--failed' },
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
 * Shows detected requirements, generated Dockerfile, approval controls,
 * and copyable run command after approval.
 */
export default function ComputeEnvironmentPanel({ environment, onApprove, approving = false }) {
  const [showDockerfile, setShowDockerfile] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!environment) return null

  const statusInfo = STATUS_CONFIG[environment.status] || STATUS_CONFIG.proposed
  const StatusIcon = statusInfo.icon
  const isProposed = environment.status === 'proposed'
  const isApproved = environment.status === 'approved'

  // Build the run command from the environment data
  const projectName = environment.project_name || environment.project_id || ''
  const runCommand = projectName ? `./compute-envs/start.sh ${projectName.toLowerCase().replace(/\s+/g, '_')}` : ''

  const handleCopy = async () => {
    if (!runCommand) return
    try {
      await navigator.clipboard.writeText(runCommand)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback
      const el = document.createElement('textarea')
      el.value = runCommand
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className={`cep-panel ${isProposed ? 'cep-panel--needs-action' : ''} ${isApproved ? 'cep-panel--approved' : ''}`}>
      <div className="cep-header">
        <Container size={16} className="cep-header-icon" />
        <span className="cep-title">Compute Environment</span>
        <span className={`cep-status ${statusInfo.className}`}>
          <StatusIcon size={12} />
          {statusInfo.label}
        </span>
      </div>

      {/* Base image */}
      {environment.base_image && (
        <div className="cep-base">
          <span className="cep-base-label">Base:</span>
          <span className="cep-base-image">{environment.base_image}</span>
          {environment.work_unit_ids?.length > 0 && (
            <span className="cep-base-units">{environment.work_unit_ids.length} work units</span>
          )}
        </div>
      )}

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

      {/* Approved — show copyable run command */}
      {isApproved && runCommand && (
        <div className="cep-run-command">
          <Terminal size={12} />
          <code className="cep-run-cmd">{runCommand}</code>
          <button className="cep-copy-btn" onClick={handleCopy} title="Copy command">
            <Copy size={12} />
            {copied ? 'Copied!' : 'Copy'}
          </button>
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
