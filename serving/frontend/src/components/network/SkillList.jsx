import { useState, useEffect, useMemo } from 'react'
import { Zap, Edit2, Filter, LayoutGrid, List, Store } from 'lucide-react'
import { getMarketplaces } from '../../api/marketplace'
import { getAggregatedSkills } from '../../api/skills'
import SkillCard from './SkillCard'
import SkillDetailModal from './SkillDetailModal'
import SkillEditModal from './SkillEditModal'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './Network.css'

// Tier display order and labels
const TIER_ORDER = ['root', 'extended']
const TIER_LABELS = {
  root: 'Core',
  extended: 'Extended'
}

function SkillList({ authorFilter, onFilterChange }) {
  const [selectedSkill, setSelectedSkill] = useState(null)
  const [editingSkill, setEditingSkill] = useState(null)
  const [marketplaces, setMarketplaces] = useState([])
  const [marketplaceFilter, setMarketplaceFilter] = useState(null)
  const [tierFilter, setTierFilter] = useState(null)
  const [viewMode, setViewMode] = useState('grid') // 'grid' or 'grouped'
  const [showFilters, setShowFilters] = useState(false)
  const [aggregatedData, setAggregatedData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Load marketplaces for filter dropdown
  useEffect(() => {
    getMarketplaces('healthy')
      .then(setMarketplaces)
      .catch(() => setMarketplaces([]))
  }, [])

  // Always load aggregated skills (includes all marketplaces)
  const loadSkills = () => {
    setLoading(true)
    getAggregatedSkills({
      marketplace_id: marketplaceFilter,
      tier: tierFilter
    })
      .then(data => {
        setAggregatedData(data)
        setError(null)
      })
      .catch(err => {
        setError(err.message || 'Failed to load skills')
        setAggregatedData(null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadSkills()
  }, [marketplaceFilter, tierFilter])

  // Apply client-side author filter
  const skills = useMemo(() => {
    const allSkills = aggregatedData?.skills || []
    if (!authorFilter) return allSkills
    return allSkills.filter(s => {
      if (authorFilter === 'system') return s.author === 'system'
      return s.author !== 'system'
    })
  }, [aggregatedData, authorFilter])

  const stats = useMemo(() => {
    const allSkills = aggregatedData?.skills || []
    const total = allSkills.length
    const system = allSkills.filter(s => s.author === 'system').length
    const user = total - system
    return { total, by_author: { system, user } }
  }, [aggregatedData])

  // Group skills by marketplace when in grouped view
  const groupedSkills = useMemo(() => {
    if (viewMode !== 'grouped') return null

    const groups = {}
    skills.forEach(skill => {
      const key = skill.marketplace_id || 'default'
      const name = skill.marketplace_name || 'Default'
      if (!groups[key]) {
        groups[key] = { name, tier: skill.marketplace_tier || 'root', skills: [] }
      }
      groups[key].skills.push(skill)
    })

    // Sort: root first, then extended
    return Object.entries(groups).sort((a, b) => {
      const tierA = TIER_ORDER.indexOf(a[1].tier)
      const tierB = TIER_ORDER.indexOf(b[1].tier)
      return (tierA === -1 ? 99 : tierA) - (tierB === -1 ? 99 : tierB)
    })
  }, [skills, viewMode])

  const handleFilterClick = (author) => {
    onFilterChange(authorFilter === author ? null : author)
  }

  const handleSkillUpdated = () => {
    loadSkills()
    setEditingSkill(null)
  }

  const handleSkillDeleted = () => {
    loadSkills()
    setEditingSkill(null)
  }

  const clearFilters = () => {
    setMarketplaceFilter(null)
    setTierFilter(null)
    onFilterChange(null)
  }

  const hasActiveFilters = marketplaceFilter || tierFilter || authorFilter

  if (loading && !skills.length) {
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
      <div className="stats-bar">
        <button
          className={`stat stat-clickable ${authorFilter === null ? 'stat-active' : ''}`}
          onClick={() => onFilterChange(null)}
        >
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">Total</span>
        </button>
        <button
          className={`stat stat-clickable ${authorFilter === 'system' ? 'stat-active' : ''}`}
          onClick={() => handleFilterClick('system')}
        >
          <span className="stat-value stat-online">{stats.by_author.system}</span>
          <span className="stat-label">System</span>
        </button>
        <button
          className={`stat stat-clickable ${authorFilter === 'user' ? 'stat-active' : ''}`}
          onClick={() => handleFilterClick('user')}
        >
          <span className="stat-value">{stats.by_author.user}</span>
          <span className="stat-label">User</span>
        </button>

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
            title="Group by marketplace"
          >
            <List size={14} />
          </button>
        </div>
      </div>

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
                <span className={`badge badge-tier badge-tier-${group.tier}`}>
                  {TIER_LABELS[group.tier] || group.tier}
                </span>
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
