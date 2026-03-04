import { Zap, Box, Puzzle } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import './Network.css'

// Tier badge styles
const TIER_CONFIG = {
  root: { icon: Box, className: 'badge-tier-root', label: 'Core' },
  extended: { icon: Puzzle, className: 'badge-tier-extended', label: 'Extended' }
}

function SkillCard({ skill, onClick }) {
  const { id, name, description, author, version, tags, marketplace_name, marketplace_tier } = skill

  const tier = marketplace_tier || 'root'
  const tierConfig = TIER_CONFIG[tier] || TIER_CONFIG.root
  const TierIcon = tierConfig.icon

  return (
    <Card className="marketplace-card" onClick={onClick}>
      <CardHeader>
        <div className="instance-info">
          <Zap size={16} className="instance-icon" />
          <span className="instance-name">{name || id}</span>
        </div>
        <div className="badge-source">
          <span className={`badge badge-tier ${tierConfig.className}`}>
            <TierIcon size={10} />
            {tierConfig.label}
          </span>
          {marketplace_name && (
            <span className="marketplace-label">{marketplace_name}</span>
          )}
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
