import { useState, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus, ArrowLeft, User, Clock, ChevronDown, ChevronUp, ChevronRight, AlertCircle, List, ListTodo, LayoutGrid, Filter, X, FolderOpen, Loader2, Info, Tag } from 'lucide-react'
import IssueFormModal from '../components/workmap/IssueFormModal'
import IssueDetailModal from '../components/workmap/IssueDetailModal'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { StatusBadge } from '../components/common/Badge'
import Badge from '../components/common/Badge'
import Spinner from '../components/common/Spinner'
import EmptyState from '../components/common/EmptyState'
import useIssues from '../hooks/useIssues'
import useCharacterizationStatuses from '../hooks/useCharacterizationStatuses'
import useBucketTree from '../hooks/useBucketTree'
import { useToast } from '../hooks/useToast'
import { useProjectContext } from '../contexts/ProjectContext'
import { deleteIssue } from '../api/workmap'
import './BacklogPage.css'

const priorityColors = {
  P0: 'error',
  P1: 'warning',
  P2: 'default',
  P3: 'info'
}

const priorityOrder = ['P0', 'P1', 'P2', 'P3']

const statusOrder = ['backlog', 'ready', 'in_progress', 'blocked', 'done', 'failed']

const statuses = [
  { value: '', label: 'All Statuses' },
  { value: 'backlog', label: 'Backlog' },
  { value: 'ready', label: 'Ready' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' }
]

const priorities = [
  { value: '', label: 'All Priorities' },
  { value: 'P0', label: 'P0 - Critical' },
  { value: 'P1', label: 'P1 - High' },
  { value: 'P2', label: 'P2 - Medium' },
  { value: 'P3', label: 'P3 - Low' }
]

const areas = [
  { value: '', label: 'All Areas' },
  { value: 'api', label: 'API' },
  { value: 'database', label: 'Database' },
  { value: 'frontend', label: 'Frontend' },
  { value: 'infra', label: 'Infrastructure' },
  { value: 'other', label: 'Other' }
]

const typeLabels = {
  feature: 'Feature',
  bug: 'Bug',
  refactor: 'Refactor',
  docs: 'Docs',
  test: 'Test'
}

const areaLabels = {
  api: 'API',
  database: 'Database',
  frontend: 'Frontend',
  infra: 'Infra',
  other: 'Other'
}

const groupByOptions = [
  { value: 'none', label: 'No Grouping' },
  { value: 'status', label: 'By Status' },
  { value: 'priority', label: 'By Priority' },
  { value: 'area', label: 'By Area' },
  { value: 'type', label: 'By Type' },
  { value: 'goal', label: 'By Goal' },
  { value: 'bucket', label: 'By Bucket' }
]

const secondaryGroupByOptions = [
  { value: 'none', label: 'None' },
  { value: 'status', label: 'By Status' },
  { value: 'priority', label: 'By Priority' },
  { value: 'area', label: 'By Area' },
  { value: 'type', label: 'By Type' },
  { value: 'goal', label: 'By Goal' },
  { value: 'bucket', label: 'By Bucket' }
]

// Helper to get grouping key(s) for an issue
const getGroupKey = (item, groupType, context = {}) => {
  let key
  switch (groupType) {
    case 'status':
      key = item.status || 'Unknown'
      break
    case 'priority':
      key = item.priority || 'Unknown'
      break
    case 'area':
      key = areaLabels[item.area] || item.area || 'Other'
      break
    case 'type':
      key = typeLabels[item.issue_type] || item.issue_type || 'Unknown'
      break
    case 'goal':
      key = item.goal_id || 'No Goal'
      break
    case 'bucket': {
      const bucketEntries = context.itemBucketMap?.[item.issue_id]
      if (bucketEntries && bucketEntries.length > 0) {
        return bucketEntries.map(b => b.name)
      }
      return ['Unassigned']
    }
    default:
      key = 'All'
  }
  return [key]
}

// Helper to sort group keys based on group type
const sortGroupKeys = (keys, groupType, context = {}) => {
  const sortedKeys = [...keys]
  if (groupType === 'status') {
    sortedKeys.sort((a, b) => statusOrder.indexOf(a) - statusOrder.indexOf(b))
  } else if (groupType === 'priority') {
    sortedKeys.sort((a, b) => priorityOrder.indexOf(a) - priorityOrder.indexOf(b))
  } else if (groupType === 'bucket') {
    const bucketRankMap = context.bucketRankMap || {}
    sortedKeys.sort((a, b) => {
      if (a === 'Unassigned') return 1
      if (b === 'Unassigned') return -1
      return (bucketRankMap[a] || 999) - (bucketRankMap[b] || 999)
    })
  } else {
    sortedKeys.sort((a, b) => {
      if (a === 'No Goal' || a === 'Unknown' || a === 'Other') return 1
      if (b === 'No Goal' || b === 'Unknown' || b === 'Other') return -1
      return a.localeCompare(b)
    })
  }
  return sortedKeys
}

const sortByOptions = [
  { value: 'created_desc', label: 'Newest First' },
  { value: 'created_asc', label: 'Oldest First' },
  { value: 'priority_desc', label: 'Priority (High→Low)' },
  { value: 'priority_asc', label: 'Priority (Low→High)' },
  { value: 'title_asc', label: 'Title (A→Z)' },
  { value: 'title_desc', label: 'Title (Z→A)' }
]

function BacklogPage() {
  const { activeProject } = useProjectContext()
  const activeProjectId = activeProject?.project_id || null
  const [searchParams, setSearchParams] = useSearchParams()
  const [refreshKey, setRefreshKey] = useState(0)
  const [viewMode, setViewMode] = useState('list')
  const [groupBy, setGroupBy] = useState('none')
  const [secondaryGroupBy, setSecondaryGroupBy] = useState('none')
  const [sortBy, setSortBy] = useState('created_desc')
  const [collapsedGroups, setCollapsedGroups] = useState({})
  const [showFilters, setShowFilters] = useState(true)

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const [selectedIssue, setSelectedIssue] = useState(null)

  // Initialize filters from URL params, scoped to active project
  const filters = useMemo(() => {
    const f = {}
    if (activeProjectId) f.project_id = activeProjectId
    const status = searchParams.get('status')
    const priority = searchParams.get('priority')
    const goalId = searchParams.get('goal_id')
    if (status) f.status = status
    if (priority) f.priority = priority
    if (goalId) f.goal_id = goalId
    return f
  }, [searchParams, activeProjectId])

  // Area filter is client-side since the API doesn't support it directly
  const areaFilter = searchParams.get('area') || ''

  const { items, stats, loading, error: loadError } = useIssues({ filters, key: refreshKey })
  const { statusMap: charStatuses } = useCharacterizationStatuses(activeProjectId)
  const { itemBucketMap, buckets: bucketList } = useBucketTree(activeProjectId)

  // Build bucket rank map for sorting bucket groups by rank order
  const bucketRankMap = useMemo(() => {
    const map = {}
    for (const bucket of bucketList) {
      const name = bucket.definition?.name || bucket.bucket_id
      map[name] = bucket.rank
    }
    return map
  }, [bucketList])

  const groupContext = useMemo(() => ({
    itemBucketMap,
    bucketRankMap
  }), [itemBucketMap, bucketRankMap])
  const toast = useToast()

  // Update URL params when filters change
  const updateUrlParams = useCallback((newFilters, newArea) => {
    const params = new URLSearchParams()
    if (newFilters.status) params.set('status', newFilters.status)
    if (newFilters.priority) params.set('priority', newFilters.priority)
    if (newFilters.goal_id) params.set('goal_id', newFilters.goal_id)
    if (newArea) params.set('area', newArea)
    setSearchParams(params, { replace: true })
  }, [setSearchParams])

  const handleFilterChange = (key, value) => {
    if (key === 'area') {
      updateUrlParams(filters, value)
    } else {
      const newFilters = { ...filters }
      if (value) {
        newFilters[key] = value
      } else {
        delete newFilters[key]
      }
      updateUrlParams(newFilters, areaFilter)
    }
  }

  const clearFilters = () => {
    setSearchParams({}, { replace: true })
  }

  const hasActiveFilters = filters.status || filters.priority || filters.goal_id || areaFilter

  // Filter and sort items
  const processedItems = useMemo(() => {
    let result = items || []

    // Apply area filter client-side
    if (areaFilter) {
      result = result.filter(item => item.area === areaFilter)
    }

    // Sort items
    result = [...result].sort((a, b) => {
      switch (sortBy) {
        case 'created_asc':
          return new Date(a.created_at) - new Date(b.created_at)
        case 'created_desc':
          return new Date(b.created_at) - new Date(a.created_at)
        case 'priority_desc':
          return priorityOrder.indexOf(a.priority) - priorityOrder.indexOf(b.priority)
        case 'priority_asc':
          return priorityOrder.indexOf(b.priority) - priorityOrder.indexOf(a.priority)
        case 'title_asc':
          return a.title.localeCompare(b.title)
        case 'title_desc':
          return b.title.localeCompare(a.title)
        default:
          return 0
      }
    })

    return result
  }, [items, areaFilter, sortBy])

  // Group items (supports two-level grouping)
  const groupedItems = useMemo(() => {
    if (groupBy === 'none') {
      return { 'All Items': { items: processedItems, subgroups: null } }
    }

    const groups = {}

    processedItems.forEach(item => {
      const primaryKeys = getGroupKey(item, groupBy, groupContext)
      primaryKeys.forEach(primaryKey => {
        if (!groups[primaryKey]) {
          groups[primaryKey] = { items: [], subgroups: null }
        }
        groups[primaryKey].items.push(item)
      })
    })

    if (secondaryGroupBy !== 'none') {
      Object.keys(groups).forEach(primaryKey => {
        const subgroups = {}
        groups[primaryKey].items.forEach(item => {
          const secondaryKeys = getGroupKey(item, secondaryGroupBy, groupContext)
          secondaryKeys.forEach(secondaryKey => {
            if (!subgroups[secondaryKey]) {
              subgroups[secondaryKey] = []
            }
            subgroups[secondaryKey].push(item)
          })
        })

        const sortedSecondaryKeys = sortGroupKeys(Object.keys(subgroups), secondaryGroupBy, groupContext)
        const sortedSubgroups = {}
        sortedSecondaryKeys.forEach(key => {
          sortedSubgroups[key] = subgroups[key]
        })
        groups[primaryKey].subgroups = sortedSubgroups
      })
    }

    const sortedPrimaryKeys = sortGroupKeys(Object.keys(groups), groupBy, groupContext)
    const sortedGroups = {}
    sortedPrimaryKeys.forEach(key => {
      sortedGroups[key] = groups[key]
    })
    return sortedGroups
  }, [processedItems, groupBy, secondaryGroupBy, groupContext])

  const toggleGroupCollapse = useCallback((groupKey) => {
    setCollapsedGroups(prev => ({
      ...prev,
      [groupKey]: !prev[groupKey]
    }))
  }, [])

  const handleIssueClick = (issue) => {
    setSelectedIssue(issue)
    setShowDetailModal(true)
  }

  const handleEditFromDetail = (issue) => {
    setSelectedIssue(issue)
    setShowDetailModal(false)
    setShowEditModal(true)
  }

  const handleModalSuccess = () => {
    setRefreshKey(k => k + 1)
    setShowDetailModal(false)
    setShowEditModal(false)
    setShowCreateModal(false)
    setSelectedIssue(null)
  }

  // Show project selection prompt if no project selected
  if (!activeProjectId) {
    return (
      <div className="page">
        <header className="page-header">
          <h1 className="page-title">Backlog</h1>
        </header>
        <EmptyState
          icon={FolderOpen}
          title="Select a Project"
          description="Please select a project from the sidebar to view backlog issues."
        />
      </div>
    )
  }

  // List view
  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">Backlog</h1>
        <div className="header-actions">
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary"
          >
            <Plus size={14} />
            New Issue
          </button>
        </div>
      </header>

      {/* Filter bar */}
      <div className="backlog-toolbar">
        <div className="toolbar-left">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`btn btn-icon ${showFilters ? 'active' : ''}`}
            title="Toggle filters"
          >
            <Filter size={16} />
          </button>
          <div className="view-toggle">
            <button
              onClick={() => setViewMode('list')}
              className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
              title="List view"
            >
              <List size={16} />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
              title="Grid view"
            >
              <LayoutGrid size={16} />
            </button>
          </div>
        </div>
        <div className="toolbar-right">
          <div className="group-selectors">
            <label className="group-label">Group:</label>
            <select
              value={groupBy}
              onChange={(e) => {
                setGroupBy(e.target.value)
                if (e.target.value === 'none' || e.target.value === secondaryGroupBy) {
                  setSecondaryGroupBy('none')
                }
                setCollapsedGroups({})
              }}
              className="toolbar-select"
            >
              {groupByOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {groupBy !== 'none' && (
              <>
                <span className="group-then">then</span>
                <select
                  value={secondaryGroupBy}
                  onChange={(e) => {
                    setSecondaryGroupBy(e.target.value)
                    setCollapsedGroups({})
                  }}
                  className="toolbar-select"
                >
                  {secondaryGroupByOptions
                    .filter(opt => opt.value !== groupBy)
                    .map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                </select>
              </>
            )}
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="toolbar-select"
          >
            {sortByOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="filters-panel">
          <div className="filters-row">
            <div className="filter-group">
              <label className="filter-label">Status</label>
              <select
                className="filter-select"
                value={filters.status || ''}
                onChange={e => handleFilterChange('status', e.target.value)}
              >
                {statuses.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">Priority</label>
              <select
                className="filter-select"
                value={filters.priority || ''}
                onChange={e => handleFilterChange('priority', e.target.value)}
              >
                {priorities.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">Area</label>
              <select
                className="filter-select"
                value={areaFilter}
                onChange={e => handleFilterChange('area', e.target.value)}
              >
                {areas.map(a => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            </div>

            {hasActiveFilters && (
              <button onClick={clearFilters} className="btn btn-link">
                <X size={14} />
                Clear filters
              </button>
            )}
          </div>
        </div>
      )}

      {/* Stats bar */}
      {stats && (
        <div className="backlog-stats">
          <span className="stat">
            <span className="stat-value">{stats.total || 0}</span>
            <span className="stat-label">Total</span>
          </span>
          <span className="stat">
            <span className="stat-value stat-pending">{(stats.by_status?.backlog || 0) + (stats.by_status?.ready || 0)}</span>
            <span className="stat-label">Pending</span>
          </span>
          <span className="stat">
            <span className="stat-value stat-progress">{stats.by_status?.in_progress || 0}</span>
            <span className="stat-label">In Progress</span>
          </span>
          <span className="stat">
            <span className="stat-value stat-blocked">{stats.by_status?.blocked || 0}</span>
            <span className="stat-label">Blocked</span>
          </span>
          <span className="stat">
            <span className="stat-value stat-done">{stats.by_status?.done || 0}</span>
            <span className="stat-label">Done</span>
          </span>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="loading-state">
          <Spinner />
        </div>
      ) : loadError ? (
        <EmptyState
          icon={AlertCircle}
          title="Failed to load backlog"
          description={loadError}
        />
      ) : processedItems.length === 0 ? (
        <EmptyState
          icon={ListTodo}
          title="No backlog issues"
          description={hasActiveFilters ? "No issues match your filters" : "Issues will appear here when goals are decomposed or issues are created manually"}
          action={hasActiveFilters ? (
            <button onClick={clearFilters} className="btn btn-secondary">
              Clear filters
            </button>
          ) : null}
        />
      ) : (
        <div className="backlog-content">
          {Object.entries(groupedItems).map(([groupName, groupData]) => {
            const isCollapsed = collapsedGroups[groupName]
            const totalItems = groupData.subgroups
              ? Object.values(groupData.subgroups).reduce((sum, items) => sum + items.length, 0)
              : groupData.items.length

            return (
              <div key={groupName} className="backlog-group">
                {groupBy !== 'none' && (
                  <div
                    className="group-header group-header-primary"
                    onClick={() => toggleGroupCollapse(groupName)}
                  >
                    <div className="group-header-left">
                      {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                      {groupBy === 'bucket' && bucketRankMap[groupName] && (
                        <span className="bucket-rank-badge">#{bucketRankMap[groupName]}</span>
                      )}
                      <h3 className="group-title">{groupName}</h3>
                      {groupBy === 'bucket' && (() => {
                        const bucket = bucketList.find(b => (b.definition?.name || b.bucket_id) === groupName)
                        return bucket?.definition?.description ? (
                          <span className="bucket-description" title={bucket.definition.description}>
                            {bucket.definition.description}
                          </span>
                        ) : null
                      })()}
                    </div>
                    <span className="group-count">{totalItems}</span>
                  </div>
                )}
                {!isCollapsed && (
                  groupData.subgroups ? (
                    <div className="backlog-subgroups">
                      {Object.entries(groupData.subgroups).map(([subgroupName, subgroupItems]) => {
                        const subgroupKey = `${groupName}::${subgroupName}`
                        const isSubgroupCollapsed = collapsedGroups[subgroupKey]

                        return (
                          <div key={subgroupKey} className="backlog-subgroup">
                            <div
                              className="group-header group-header-secondary"
                              onClick={() => toggleGroupCollapse(subgroupKey)}
                            >
                              <div className="group-header-left">
                                {isSubgroupCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                                <h4 className="subgroup-title">{subgroupName}</h4>
                              </div>
                              <span className="group-count">{subgroupItems.length}</span>
                            </div>
                            {!isSubgroupCollapsed && (
                              <div className={viewMode === 'list' ? 'backlog-list' : 'backlog-grid'}>
                                {subgroupItems.map(issue => (
                                  <BacklogItem
                                    key={issue.issue_id}
                                    issue={issue}
                                    viewMode={viewMode}
                                    characterization={charStatuses[issue.issue_id]}
                                    onClick={() => handleIssueClick(issue)}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className={viewMode === 'list' ? 'backlog-list' : 'backlog-grid'}>
                      {groupData.items.map(issue => (
                        <BacklogItem
                          key={issue.issue_id}
                          issue={issue}
                          viewMode={viewMode}
                          characterization={charStatuses[issue.issue_id]}
                          onClick={() => handleIssueClick(issue)}
                        />
                      ))}
                    </div>
                  )
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Create Issue Modal */}
      <IssueFormModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={handleModalSuccess}
        projectId={activeProjectId}
      />

      {/* Edit Issue Modal */}
      <IssueFormModal
        isOpen={showEditModal}
        onClose={() => { setShowEditModal(false); setSelectedIssue(null) }}
        issue={selectedIssue}
        onSuccess={handleModalSuccess}
      />

      {/* Issue Detail Modal */}
      <IssueDetailModal
        isOpen={showDetailModal}
        onClose={() => { setShowDetailModal(false); setSelectedIssue(null) }}
        issue={selectedIssue}
        onEdit={handleEditFromDetail}
        onSuccess={handleModalSuccess}
      />
    </div>
  )
}

// Characterization status badge with tooltip
const charStatusConfig = {
  pending: { label: 'Pending', className: 'char-pending' },
  in_progress: { label: 'Analyzing', className: 'char-in-progress' },
  completed: { label: 'Characterized', className: 'char-completed' },
  failed: { label: 'Failed', className: 'char-failed' },
}

function CharacterizationBadge({ status }) {
  if (!status) return null
  const config = charStatusConfig[status] || charStatusConfig.pending

  const isActive = status === 'pending' || status === 'in_progress'

  return (
    <span className={`char-badge ${config.className}`} title="AI characterization assigns ontology tags, meaning assessments, and dependency analysis to this issue">
      {isActive ? <Loader2 size={10} className="char-spinner" /> : <Tag size={10} />}
      <span>{config.label}</span>
    </span>
  )
}

// Ontology tag pills displayed after characterization completes
function OntologyTagsDisplay({ tags }) {
  if (!tags?.universal) return null

  const { work_type, lifecycle_stage, technical_domains } = tags.universal
  const allTags = [
    work_type?.replace(/_/g, ' '),
    lifecycle_stage,
    ...(technical_domains || []),
  ].filter(Boolean)

  if (allTags.length === 0) return null

  return (
    <div className="ontology-tags">
      {allTags.slice(0, 3).map(tag => (
        <span key={tag} className="ontology-tag">{tag}</span>
      ))}
      {allTags.length > 3 && (
        <span className="ontology-tag-more">+{allTags.length - 3}</span>
      )}
    </div>
  )
}

// Strips the 'issue_' prefix and returns the first 8 hex chars for display
const formatIssueId = (issueId) => {
  if (!issueId) return ''
  const prefix = 'issue_'
  const hash = issueId.startsWith(prefix) ? issueId.slice(prefix.length) : issueId
  return hash.slice(0, 8)
}

// Backlog item component for list/grid view - displays Issue objects
function BacklogItem({ issue, viewMode, characterization, onClick }) {
  const {
    issue_id,
    title,
    description,
    status,
    priority,
    issue_type,
    area,
    assigned_compute_id,
    depends_on,
    required_skills
  } = issue

  const hasDependencies = depends_on && depends_on.length > 0
  const charStatus = characterization?.status
  const charTags = characterization?.ontology_tags

  const handleCopyId = (e) => {
    e.stopPropagation()
    if (issue_id) navigator.clipboard.writeText(issue_id)
  }

  if (viewMode === 'list') {
    return (
      <div className="backlog-item-list" onClick={onClick}>
        <div className="item-main">
          <div className="item-title-row">
            {issue_id && (
              <span
                className="issue-id-chip"
                onClick={handleCopyId}
                title={`Click to copy: ${issue_id}`}
              >
                {formatIssueId(issue_id)}
              </span>
            )}
            <span className="item-title">{title}</span>
            <StatusBadge status={status} />
            <CharacterizationBadge status={charStatus} />
          </div>
          {description && (
            <p className="item-description">{description}</p>
          )}
          {charStatus === 'completed' && <OntologyTagsDisplay tags={charTags} />}
        </div>
        <div className="item-meta">
          <Badge variant={priorityColors[priority] || 'default'} size="sm">
            {priority}
          </Badge>
          <Badge variant="default" size="sm">{typeLabels[issue_type] || issue_type}</Badge>
          {area && area !== 'other' && (
            <Badge variant="default" size="sm">{areaLabels[area] || area}</Badge>
          )}
          {required_skills?.slice(0, 2).map(skill => (
            <span key={skill} className="item-tag">
              {skill}
            </span>
          ))}
          {required_skills?.length > 2 && (
            <span className="item-tag-more">+{required_skills.length - 2}</span>
          )}
        </div>
        <div className="item-details">
          {assigned_compute_id && (
            <span className="detail-chip">
              <User size={12} />
              {assigned_compute_id.slice(0, 8)}
            </span>
          )}
          {hasDependencies && (
            <span className="detail-chip">
              <AlertCircle size={12} />
              {depends_on.length} dep{depends_on.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
    )
  }

  // Grid view (card)
  return (
    <div className="backlog-item-card" onClick={onClick}>
      <div className="card-header">
        <span className="item-title">{title}</span>
        <div className="card-header-badges">
          <StatusBadge status={status} />
          <CharacterizationBadge status={charStatus} />
        </div>
      </div>
      {issue_id && (
        <span
          className="issue-id-chip"
          onClick={handleCopyId}
          title={`Click to copy: ${issue_id}`}
        >
          {formatIssueId(issue_id)}
        </span>
      )}
      {description && (
        <p className="item-description">{description}</p>
      )}
      {charStatus === 'completed' && <OntologyTagsDisplay tags={charTags} />}
      <div className="card-meta">
        <Badge variant={priorityColors[priority] || 'default'}>
          {priority}
        </Badge>
        <Badge variant="default">{typeLabels[issue_type] || issue_type}</Badge>
        {area && area !== 'other' && (
          <Badge variant="default">{areaLabels[area] || area}</Badge>
        )}
      </div>
      <div className="card-details">
        {assigned_compute_id && (
          <span className="detail-chip">
            <User size={12} />
            <span className="mono">{assigned_compute_id.slice(0, 12)}</span>
          </span>
        )}
      </div>
      {required_skills?.length > 0 && (
        <div className="card-tags">
          {required_skills.slice(0, 3).map(skill => (
            <span key={skill} className="item-tag">
              {skill}
            </span>
          ))}
          {required_skills.length > 3 && (
            <span className="item-tag-more">+{required_skills.length - 3}</span>
          )}
        </div>
      )}
      {hasDependencies && (
        <div className="blocker-indicator">
          <AlertCircle size={12} />
          <span>{depends_on.length} dependenc{depends_on.length > 1 ? 'ies' : 'y'}</span>
        </div>
      )}
    </div>
  )
}

export { formatIssueId }
export default BacklogPage
