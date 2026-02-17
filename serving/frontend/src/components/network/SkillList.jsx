import { useState, useEffect, useMemo } from 'react'
import { Zap, Edit2, Filter, LayoutGrid, List, Store } from 'lucide-react'
import useSkills from '../../hooks/useSkills'
import { getMarketplaces } from '../../api/marketplace'
import { getAggregatedSkills } from '../../api/skills'
import SkillCard from './SkillCard'
import SkillDetailModal from './SkillDetailModal'
import SkillEditModal from './SkillEditModal'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './Network.css'

// Tier display order and labels
const TIER_ORDER = ['root', 'enterprise', 'team', 'project', 'user']
const TIER_LABELS = {
  root: 'Root',
  enterprise: 'Enterprise',
  team: 'Team',
  project: 'Project',
  user: 'User'
}

function SkillList({ authorFilter, onFilterChange }) {
  const { skills: defaultSkills, stats, loading, error, refresh } = useSkills({ filter: authorFilter ? { author: authorFilter } : null })

  const [selectedSkill, setSelectedSkill] = useState(null)
  const [editingSkill, setEditingSkill] = useState(null)
  const [marketplaces, setMarketplaces] = useState([])
  const [marketplaceFilter, setMarketplaceFilter] = useState(null)
  const [tierFilter, setTierFilter] = useState(null)
  const [viewMode, setViewMode] = useState('grid') // 'grid' or 'grouped'
  const [showFilters, setShowFilters] = useState(false)
  const [aggregatedSkills, setAggregatedSkills] = useState(null)
  const [aggregatedLoading, setAggregatedLoading] = useState(false)

  // Load marketplaces for filter dropdown
  useEffect(() => {
    getMarketplaces('healthy')
      .then(setMarketplaces)
      .catch(() => setMarketplaces([]))
  }, [])

  // Load aggregated skills when filters change
  useEffect(() => {
    if (marketplaceFilter || tierFilter) {
      setAggregatedLoading(true)
      getAggregatedSkills({
        marketplace_id: marketplaceFilter,
        tier: tierFilter
      })
        .then(data => {
          setAggregatedSkills(data)
          setAggregatedLoading(false)
        })
        .catch(() => {
          setAggregatedSkills(null)
          setAggregatedLoading(false)
        })
    } else {
      setAggregatedSkills(null)
    }
  }, [marketplaceFilter, tierFilter])

  // Use aggregated skills when filtered, otherwise use default
  const skills = useMemo(() => {
    if (aggregatedSkills) {
      return aggregatedSkills.skills || []
    }
    return defaultSkills
  }, [aggregatedSkills, defaultSkills])

  // Group skills by marketplace when in grouped view
  const groupedSkills = useMemo(() => {
    if (viewMode !== 'grouped') return null

    const groups = {}
    skills.forEach(skill => {
      const key = skill.marketplace_id || 'default'
      const name = skill.marketplace_name || 'Default'
      if (!groups[key]) {
        groups[key] = { name, tier: skill.marketplace_tier, skills: [] }
      }
      groups[key].skills.push(skill)
    })

    // Sort by tier order
    return Object.entries(groups).sort((a, b) => {
      const tierA = TIER_ORDER.indexOf(a[1].tier || 'user')
      const tierB = TIER_ORDER.indexOf(b[1].tier || 'user')
      return tierA - tierB
    })
  }, [skills, viewMode])

  const handleFilterClick = (author) => {
    onFilterChange(authorFilter === author ? null : author)
  }

  const handleSkillUpdated = () => {
    refresh()
    setEditingSkill(null)
  }

  const handleSkillDeleted = () => {
    refresh()
    setEditingSkill(null)
  }

  const clearFilters = () => {
    setMarketplaceFilter(null)
    setTierFilter(null)
    onFilterChange(null)
  }

  const hasActiveFilters = marketplaceFilter || tierFilter || authorFilter

  if ((loading || aggregatedLoading) && !skills.length) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={Zap}
        title="Failed to load skills"
        description={error}
      />
    )
  }

  return (
    <div className="network-section">
      {/* Stats bar with author filters */}
      {stats && (
        <div className="stats-bar">
          <button
            className={`stat stat-clickable ${authorFilter === null ? 'stat-active' : ''}`}
            onClick={() => onFilterChange(null)}
          >
            <span className="stat-value">{aggregatedSkills?.total || stats.total || 0}</span>
            <span className="stat-label">Total</span>
          </button>
          <button
            className={`stat stat-clickable ${authorFilter === 'system' ? 'stat-active' : ''}`}
            onClick={() => handleFilterClick('system')}
          >
            <span className="stat-value stat-online">{aggregatedSkills?.by_author?.system || stats.by_author?.system || 0}</span>
            <span className="stat-label">System</span>
          </button>
          {(stats.by_author || aggregatedSkills?.by_author) && (
            <button
              className={`stat stat-clickable ${authorFilter && authorFilter !== 'system' ? 'stat-active' : ''}`}
              onClick={() => {
                const userAuthor = Object.keys(stats.by_author || {}).find(a => a !== 'system')
                handleFilterClick(userAuthor || 'user')
              }}
            >
              <span className="stat-value">{aggregatedSkills?.by_author?.user || Object.keys(stats.by_author || {}).reduce((sum, author) => {
                return author !== 'system' ? sum + (stats.by_author[author] || 0) : sum
              }, 0)}</span>
              <span className="stat-label">User</span>
            </button>
          )}

          {/* View mode and filter toggles */}
          <div className="stats-actions">
            <button
              className={`icon-btn ${showFilters ? 'icon-btn-active' : ''}`}
              onClick={() => setShowFilters(!showFilters)}
              title="Toggle filters"
            >
              <Filter size={14} />
              {hasActiveFilters && <span className="filter-badge" />}
            </button>
            <button
              className={`icon-btn ${viewMode === 'grid' ? 'icon-btn-active' : ''}`}
              onClick={() => setViewMode('grid')}
              title="Grid view"
            >
              <LayoutGrid size={14} />
            </button>
            <button
              className={`icon-btn ${viewMode === 'grouped' ? 'icon-btn-active' : ''}`}
              onClick={() => setViewMode('grouped')}
              title="Group by skill source"
            >
              <List size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Filter panel */}
      {showFilters && (
        <div className="filter-panel">
          <div className="filter-group">
            <label className="filter-label">Source</label>
            <select
              className="filter-select"
              value={marketplaceFilter || ''}
              onChange={(e) => setMarketplaceFilter(e.target.value || null)}
            >
              <option value="">All Sources</option>
              {marketplaces.map(m => (
                <option key={m.marketplace_id} value={m.marketplace_id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label className="filter-label">Tier</label>
            <select
              className="filter-select"
              value={tierFilter || ''}
              onChange={(e) => setTierFilter(e.target.value || null)}
            >
              <option value="">All Tiers</option>
              {TIER_ORDER.map(tier => (
                <option key={tier} value={tier}>{TIER_LABELS[tier]}</option>
              ))}
            </select>
          </div>
          {hasActiveFilters && (
            <button className="filter-clear" onClick={clearFilters}>
              Clear Filters
            </button>
          )}
        </div>
      )}

      {/* Skills display */}
      {skills.length === 0 ? (
        <EmptyState
          icon={Zap}
          title={hasActiveFilters ? "No skills match filters" : "No skills"}
          description={hasActiveFilters ? "Try adjusting your filters" : "Skills will appear here when they are registered"}
        />
      ) : viewMode === 'grouped' && groupedSkills ? (
        <div className="grouped-skills">
          {groupedSkills.map(([marketplaceId, group]) => (
            <div key={marketplaceId} className="skill-group">
              <div className="skill-group-header">
                <Store size={14} />
                <span className="skill-group-name">{group.name}</span>
                {group.tier && (
                  <span className={`badge badge-tier badge-tier-${group.tier}`}>
                    {TIER_LABELS[group.tier]}
                  </span>
                )}
                <span className="skill-group-count">{group.skills.length} skills</span>
              </div>
              <div className="card-grid">
                {group.skills.map(skill => (
                  <SkillCard
                    key={skill.id}
                    skill={skill}
                    onClick={() => setSelectedSkill(skill.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card-grid">
          {skills.map(skill => (
            <SkillCard
              key={skill.id}
              skill={skill}
              onClick={() => setSelectedSkill(skill.id)}
            />
          ))}
        </div>
      )}

      {/* Detail Modal with Edit button */}
      <SkillDetailModal
        isOpen={!!selectedSkill && !editingSkill}
        onClose={() => setSelectedSkill(null)}
        skillId={selectedSkill}
        onEdit={() => setEditingSkill(selectedSkill)}
      />

      {/* Edit Modal */}
      <SkillEditModal
        isOpen={!!editingSkill}
        onClose={() => setEditingSkill(null)}
        skillId={editingSkill}
        onUpdated={handleSkillUpdated}
        onDeleted={handleSkillDeleted}
      />
    </div>
  )
}

export default SkillList
