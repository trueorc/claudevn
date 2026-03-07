import { Server, Cpu, MemoryStick, HardDrive } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import { StatusBadge } from '../common/Badge'
import AuthBadge from '../auth/AuthBadge'
import './Network.css'

function ResourceBar({ value, max, label }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  const color = pct >= 90 ? 'var(--status-offline)' : pct >= 70 ? 'var(--status-degraded)' : 'var(--status-online)'
  return (
    <div className="resource-bar-row" title={`${label}: ${value}`}>
      <div className="resource-bar-track">
        <div className="resource-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

function ComputeCard({ instance, onClick, authInfo, onAuthClick }) {
  const { instance_id, name, status, capabilities, last_heartbeat, project_ids, lifecycle_mode } = instance

  const agentCount = capabilities?.agents?.length || 0
  const toolCount = capabilities?.tools?.length || 0
  const resources = capabilities?.resources
  const runtimes = (capabilities?.tools_available || []).filter(t => t.startsWith('runtime:'))
  const isDraining = status === 'draining'
  const isBenched = !isDraining && (!project_ids || project_ids.length === 0)
  const isAllProjects = project_ids?.includes('*')
  const isManaged = lifecycle_mode === 'managed'

  const cardClassName = `compute-card${isBenched ? ' compute-benched' : ''}${isDraining ? ' compute-draining' : ''}`

  const hasResources = resources && (resources.cpu_count != null || resources.memory_gb != null || resources.storage_gb != null)

  return (
    <Card className={cardClassName} onClick={onClick}>
      <CardHeader>
        <div className="instance-info">
          <Server size={16} className="instance-icon" />
          <span className="instance-name">{name || instance_id}</span>
        </div>
        <div className="badge-group">
          {isManaged && <span className="lifecycle-badge managed">managed</span>}
          <AuthBadge authInfo={authInfo} onClick={onAuthClick} />
          <StatusBadge status={isBenched ? 'benched' : status} />
        </div>
      </CardHeader>
      <CardBody>
        <div className="instance-meta">
          <span className="meta-item">
            <span className="meta-label">ID:</span>
            <span className="meta-value mono">{instance_id}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Agents:</span>
            <span className="meta-value">{agentCount}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Projects:</span>
            <span className="meta-value">
              {isBenched ? 'None' : isAllProjects ? 'All' : project_ids.length}
            </span>
          </span>
        </div>
        {hasResources && (
          <div className="resource-metrics">
            {resources.cpu_count != null && (
              <div className="resource-metric">
                <Cpu size={11} className="resource-metric-icon" />
                <span className="resource-metric-value">{resources.cpu_count} CPU</span>
              </div>
            )}
            {resources.memory_gb != null && (
              <div className="resource-metric">
                <MemoryStick size={11} className="resource-metric-icon" />
                <span className="resource-metric-value">{resources.memory_gb} GB</span>
              </div>
            )}
            {resources.storage_gb != null && (
              <div className="resource-metric">
                <HardDrive size={11} className="resource-metric-icon" />
                <span className="resource-metric-value">{resources.storage_gb} GB</span>
              </div>
            )}
            {resources.gpu_count > 0 && (
              <div className="resource-metric">
                <Cpu size={11} className="resource-metric-icon" />
                <span className="resource-metric-value">{resources.gpu_count} GPU{resources.gpu_type ? ` (${resources.gpu_type})` : ''}</span>
              </div>
            )}
          </div>
        )}
        {runtimes.length > 0 && (
          <div className="runtime-tags">
            {runtimes.map(rt => (
              <span key={rt} className="runtime-tag">{rt.replace('runtime:', '')}</span>
            ))}
          </div>
        )}
        {last_heartbeat && (
          <div className="last-seen">
            Last seen: {new Date(last_heartbeat).toLocaleTimeString()}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export default ComputeCard
