import { Server } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import { StatusBadge } from '../common/Badge'
import AuthBadge from '../auth/AuthBadge'
import './Network.css'

function ComputeCard({ instance, onClick, authInfo, onAuthClick }) {
  const { instance_id, name, status, capabilities, last_heartbeat, project_ids } = instance

  const agentCount = capabilities?.agents?.length || 0
  const toolCount = capabilities?.tools?.length || 0
  const isDraining = status === 'draining'
  const isBenched = !isDraining && (!project_ids || project_ids.length === 0)
  const isAllProjects = project_ids?.includes('*')

  const cardClassName = `compute-card${isBenched ? ' compute-benched' : ''}${isDraining ? ' compute-draining' : ''}`

  return (
    <Card className={cardClassName} onClick={onClick}>
      <CardHeader>
        <div className="instance-info">
          <Server size={16} className="instance-icon" />
          <span className="instance-name">{name || instance_id}</span>
        </div>
        <div className="badge-group">
          <AuthBadge authInfo={authInfo} onClick={onAuthClick} />
          <StatusBadge status={isBenched ? 'benched' : status} />
        </div>
      </CardHeader>
      <CardBody>
        <div className="instance-meta">
          <span className="meta-item">
            <span className="meta-label">ID:</span>
            <span className="meta-value mono">{instance_id?.slice(0, 12)}</span>
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
