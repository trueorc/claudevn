import { useState, useEffect } from 'react'
import { Zap, Edit2, Building2, Users, FolderKanban, User } from 'lucide-react'
import Modal from '../common/Modal'
import { getSkill } from '../../api/skills'
import '../common/Modal.css'
import './Network.css'

// Tier icons and labels
const TIER_CONFIG = {
  root: { icon: Zap, className: 'badge-tier-root', label: 'Root' },
  enterprise: { icon: Building2, className: 'badge-tier-enterprise', label: 'Enterprise' },
  team: { icon: Users, className: 'badge-tier-team', label: 'Team' },
  project: { icon: FolderKanban, className: 'badge-tier-project', label: 'Project' },
  user: { icon: User, className: 'badge-tier-user', label: 'User' }
}

function SkillDetailModal({ isOpen, onClose, skillId, onEdit }) {
  const [skill, setSkill] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (isOpen && skillId) {
      setLoading(true)
      setError(null)
      getSkill(skillId)
        .then(setSkill)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }
  }, [isOpen, skillId])

  if (!isOpen) return null

  const isSystem = skill?.author === 'system'
  const tier = skill?.marketplace_tier || (isSystem ? 'root' : 'user')
  const tierConfig = TIER_CONFIG[tier] || TIER_CONFIG.user
  const TierIcon = tierConfig.icon

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Skill" width="600px">
      {loading ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading...
        </div>
      ) : error ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--status-offline)' }}>
          {error}
        </div>
      ) : skill ? (
        <div className="detail-content">
          <div className="detail-header">
            <Zap size={20} style={{ color: 'var(--text-muted)' }} />
            <span className="detail-name">{skill.name || skill.id}</span>
            <div className="badge-group">
              {skill.marketplace_name && (
                <span className={`badge badge-tier ${tierConfig.className}`} title={`From: ${skill.marketplace_name}`}>
                  <TierIcon size={10} />
                  {tierConfig.label}
                </span>
              )}
              <span className={`badge ${isSystem ? 'badge-system' : 'badge-user'}`}>
                {isSystem ? 'system' : 'user'}
              </span>
            </div>
          </div>

          <div className="detail-section">
            <div className="detail-row">
              <span className="detail-label">Skill ID</span>
              <span className="detail-value mono">{skill.id}</span>
            </div>
            {skill.description && (
              <div className="detail-row">
                <span className="detail-label">Description</span>
                <span className="detail-value">{skill.description}</span>
              </div>
            )}
            <div className="detail-row">
              <span className="detail-label">Author</span>
              <span className="detail-value">{skill.author}</span>
            </div>
            {skill.version && (
              <div className="detail-row">
                <span className="detail-label">Version</span>
                <span className="detail-value">{skill.version}</span>
              </div>
            )}
          </div>

          {skill.instructions && (
            <div className="detail-section">
              <h4 className="detail-section-title">Instructions</h4>
              <div className="detail-instructions">
                {skill.instructions.length > 500
                  ? `${skill.instructions.substring(0, 500)}...`
                  : skill.instructions}
              </div>
            </div>
          )}

          {skill.tools && skill.tools.length > 0 && (
            <div className="detail-section">
              <h4 className="detail-section-title">Tools</h4>
              <div className="detail-list">
                {skill.tools.map(tool => (
                  <span key={tool} className="detail-list-item">{tool}</span>
                ))}
              </div>
            </div>
          )}

          {skill.tags && skill.tags.length > 0 && (
            <div className="detail-section">
              <h4 className="detail-section-title">Tags</h4>
              <div className="detail-list">
                {skill.tags.map(tag => (
                  <span key={tag} className="tag">{tag}</span>
                ))}
              </div>
            </div>
          )}

          {skill.constraints && skill.constraints.length > 0 && (
            <div className="detail-section">
              <h4 className="detail-section-title">Constraints</h4>
              <div className="detail-list">
                {skill.constraints.map((constraint, idx) => (
                  <span key={idx} className="detail-list-item">{constraint}</span>
                ))}
              </div>
            </div>
          )}

          {skill.conflicts && skill.conflicts.length > 0 && (
            <div className="detail-section">
              <h4 className="detail-section-title">Conflicts</h4>
              <div className="detail-list">
                {skill.conflicts.map((conflict, idx) => (
                  <span key={idx} className="detail-list-item">{conflict}</span>
                ))}
              </div>
            </div>
          )}

          {skill.marketplace_name && (
            <div className="detail-section">
              <h4 className="detail-section-title">Source</h4>
              <div className="detail-row">
                <span className="detail-label">Source</span>
                <span className="detail-value">{skill.marketplace_name}</span>
              </div>
              {skill.marketplace_id && (
                <div className="detail-row">
                  <span className="detail-label">Source ID</span>
                  <span className="detail-value mono">{skill.marketplace_id}</span>
                </div>
              )}
            </div>
          )}

          {/* Edit button for non-system skills */}
          <div className="detail-actions">
            <button
              className="btn btn-secondary"
              onClick={onEdit}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-xs)' }}
            >
              <Edit2 size={14} />
              {isSystem ? 'View Details' : 'Edit Skill'}
            </button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}

export default SkillDetailModal
