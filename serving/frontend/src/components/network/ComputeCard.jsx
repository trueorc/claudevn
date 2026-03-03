import { Server } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import { StatusBadge } from '../common/Badge'
import AuthBadge from '../auth/AuthBadge'
import './Network.css'

function ComputeCard({ instance, onClick, authInfo, onAuthClick }) {
  const { instance_id, name, status, capabilities, last_heartbeat, project_ids, lifecycle_mode } = instance

  const agentCount = capabilities?.agents?.length || 0
  const toolCount = capabilities?.tools?.length || 0
  const runtimes = (capabilities?.tools_available || []).filter(t => t.startsWith('runtime:'))
  const isDraining = status === 'draining'
  const isBenched = !isDraining && (!project_ids || project_ids.length === 0)
  const isAllProjects = project_ids?.includes('*')
  const isManaged = lifecycle_mode === 'managed'

  const cardClassName = `compute-card${isBenched ? ' compute-benched' : ''}${isDraining ? ' compute-draining' : ''}`

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
