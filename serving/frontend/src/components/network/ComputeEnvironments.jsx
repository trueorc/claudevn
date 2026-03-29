import { useState, useEffect, useCallback } from 'react'
import { Container, CheckCircle2, Clock, AlertTriangle, Play, XCircle, ChevronDown, ChevronRight, Eye } from 'lucide-react'
import { request } from '../../api/index'
import './ComputeEnvironments.css'

const STATUS_CONFIG = {
  proposed: { icon: Clock, label: 'Proposed', className: 'ce-env--proposed' },
  approved: { icon: CheckCircle2, label: 'Approved', className: 'ce-env--approved' },
  building: { icon: Clock, label: 'Building', className: 'ce-env--building' },
  ready: { icon: CheckCircle2, label: 'Ready', className: 'ce-env--ready' },
  active: { icon: Play, label: 'Active', className: 'ce-env--active' },
  failed: { icon: XCircle, label: 'Failed', className: 'ce-env--failed' },
  retired: { icon: Clock, label: 'Retired', className: 'ce-env--retired' },
}

function EnvironmentCard({ env }) {
  const [expanded, setExpanded] = useState(false)
  const config = STATUS_CONFIG[env.status] || STATUS_CONFIG.proposed
  const StatusIcon = config.icon

  return (
    <div className={`ce-card ${config.className}`}>
      <button className="ce-card-header" onClick={() => setExpanded(!expanded)}>
        <Container size={14} />
        <span className="ce-card-id">{env.id}</span>
        <span className="ce-card-project">{env.project_id}</span>
        <span className={`ce-card-status ${config.className}`}>
          <StatusIcon size={12} />
          {config.label}
        </span>
        {env.image_tag && <span className="ce-card-tag">{env.image_tag}</span>}
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {expanded && (
        <div className="ce-card-body">
          <div className="ce-card-meta">
            <span>Base: <strong>{env.base_image}</strong></span>
            <span>Units: {env.work_unit_ids?.length || 0}</span>
          </div>

          {env.requirements?.length > 0 && (
            <div className="ce-card-reqs">
              <span className="ce-card-label">Requirements:</span>
              <div className="ce-req-tags">
                {env.requirements.map((r, i) => (
                  <span key={i} className="ce-req-tag">
                    {r.name}{r.version ? ` ${r.version}` : ''}
                  </span>
                ))}
              </div>
            </div>
          )}

          {env.dockerfile_content && (
            <details className="ce-card-dockerfile">
              <summary><Eye size={12} /> Dockerfile</summary>
              <pre>{env.dockerfile_content}</pre>
            </details>
          )}

          {env.container_id && (
            <div className="ce-card-container">
              <span className="ce-card-label">Container:</span>
              <span className="ce-card-container-id">{env.container_id}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Compute environments section for the Network page.
 * Shows all approved/building/ready/active environments
 * with their Docker specs and container status.
 */
export default function ComputeEnvironments({ projectId }) {
  const [environments, setEnvironments] = useState([])
  const [loading, setLoading] = useState(true)

  const loadEnvironments = useCallback(async () => {
    try {
      // TODO: dedicated endpoint for listing all project environments
      // For now, stub with empty
      setEnvironments([])
    } catch {
      setEnvironments([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadEnvironments() }, [loadEnvironments])

  const activeCount = environments.filter(e => e.status === 'active').length
  const readyCount = environments.filter(e => e.status === 'ready').length
  const buildingCount = environments.filter(e => e.status === 'building').length

  return (
    <div className="ce-section">
      <div className="ce-section-header">
        <Container size={16} />
        <h2>Compute Environments</h2>
        <div className="ce-section-stats">
          {activeCount > 0 && <span className="ce-stat ce-stat--active"><Play size={12} /> {activeCount} active</span>}
          {readyCount > 0 && <span className="ce-stat ce-stat--ready"><CheckCircle2 size={12} /> {readyCount} ready</span>}
          {buildingCount > 0 && <span className="ce-stat ce-stat--building"><Clock size={12} /> {buildingCount} building</span>}
        </div>
      </div>

      {loading ? (
        <p className="ce-empty">Loading environments...</p>
      ) : environments.length === 0 ? (
        <div className="ce-empty-state">
          <Container size={24} />
          <p>No compute environments provisioned yet.</p>
          <p className="ce-empty-hint">Environments are created during planning — go to the Plan page to decompose a goal and the system will detect what runtime tools are needed.</p>
        </div>
      ) : (
        <div className="ce-list">
          {environments.map(env => (
            <EnvironmentCard key={env.id} env={env} />
          ))}
        </div>
      )}
    </div>
  )
}
