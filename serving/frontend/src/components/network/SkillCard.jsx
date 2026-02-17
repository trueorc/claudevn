import { Zap, Building2, Users, FolderKanban, User } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import './Network.css'

// Tier icons and colors
const TIER_CONFIG = {
  root: { icon: Zap, className: 'badge-tier-root', label: 'Root' },
  enterprise: { icon: Building2, className: 'badge-tier-enterprise', label: 'Enterprise' },
  team: { icon: Users, className: 'badge-tier-team', label: 'Team' },
  project: { icon: FolderKanban, className: 'badge-tier-project', label: 'Project' },
  user: { icon: User, className: 'badge-tier-user', label: 'User' }
}

function SkillCard({ skill, onClick }) {
  const { id, name, description, author, version, tags, marketplace_name, marketplace_tier } = skill

  const isSystem = author === 'system'
  const tier = marketplace_tier || (isSystem ? 'root' : 'user')
  const tierConfig = TIER_CONFIG[tier] || TIER_CONFIG.user
  const TierIcon = tierConfig.icon

  return (
    <Card className="marketplace-card" onClick={onClick}>
      <CardHeader>
        <div className="instance-info">
          <Zap size={16} className="instance-icon" />
          <span className="instance-name">{name || id}</span>
        </div>
        <div className="badge-group">
          {marketplace_name && (
            <span className={`badge badge-tier ${tierConfig.className}`} title={`From: ${marketplace_name}`}>
              <TierIcon size={10} />
              {tierConfig.label}
            </span>
          )}
          <span className={`badge ${isSystem ? 'badge-system' : 'badge-user'}`}>
            {isSystem ? 'system' : 'user'}
          </span>
        </div>
      </CardHeader>
      <CardBody>
        {description && (
          <div className="skill-description">
            {description}
          </div>
        )}
        <div className="instance-meta">
          <span className="meta-item">
            <span className="meta-label">Author:</span>
            <span className="meta-value">{author}</span>
          </span>
          {version && (
            <span className="meta-item">
              <span className="meta-label">Version:</span>
              <span className="meta-value">{version}</span>
            </span>
          )}
        </div>
        {tags && tags.length > 0 && (
          <div className="skill-tags">
            {tags.map(tag => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export default SkillCard
