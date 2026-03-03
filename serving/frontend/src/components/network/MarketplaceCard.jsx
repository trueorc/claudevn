import { Store, Zap, Building2, Users, FolderKanban, User } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import { StatusBadge } from '../common/Badge'
import './Network.css'

// Tier icons and labels
const TIER_CONFIG = {
  root: { icon: Zap, className: 'badge-tier-root', label: 'Root' },
  enterprise: { icon: Building2, className: 'badge-tier-enterprise', label: 'Enterprise' },
  team: { icon: Users, className: 'badge-tier-team', label: 'Team' },
  project: { icon: FolderKanban, className: 'badge-tier-project', label: 'Project' },
  user: { icon: User, className: 'badge-tier-user', label: 'User' }
}

function MarketplaceCard({ marketplace, onClick }) {
  const { marketplace_id, name, status, tier, capabilities, last_heartbeat } = marketplace

  const agentCount = capabilities?.agent_count || 0
  const toolCount = capabilities?.tool_count || 0
  const skillCount = capabilities?.skill_count || 0

  const tierConfig = TIER_CONFIG[tier] || TIER_CONFIG.user
  const TierIcon = tierConfig.icon

  return (
    <Card className="marketplace-card" onClick={onClick}>
      <CardHeader>
        <div className="instance-info">
          <Store size={16} className="instance-icon" />
          <span className="instance-name">{name || marketplace_id}</span>
        </div>
        <div className="badge-group">
          {tier && (
            <span className={`badge badge-tier ${tierConfig.className}`}>
              <TierIcon size={10} />
              {tierConfig.label}
            </span>
          )}
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardBody>
        <div className="instance-meta">
          <span className="meta-item">
            <span className="meta-label">ID:</span>
            <span className="meta-value mono">{marketplace_id}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Skills:</span>
            <span className="meta-value">{skillCount}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Agents:</span>
            <span className="meta-value">{agentCount}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Tools:</span>
            <span className="meta-value">{toolCount}</span>
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

export default MarketplaceCard
