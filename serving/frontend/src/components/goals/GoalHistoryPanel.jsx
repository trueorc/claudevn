import { useState, useMemo, useCallback } from 'react'
import { Clock, ChevronRight, Search, Filter, MessageSquare, X, ArrowUpDown, Trash2, Archive, ArchiveRestore } from 'lucide-react'
import EvaluationStatusIndicator from './EvaluationStatusIndicator'

/**
 * Truncates text at word boundary to avoid cutting words mid-way.
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length before truncation
 * @returns {string} - Truncated text with ellipsis if needed
 */
function truncateAtWordBoundary(text, maxLength) {
  if (!text || text.length <= maxLength) return text
  // Find the last space before maxLength
  const truncated = text.slice(0, maxLength)
  const lastSpace = truncated.lastIndexOf(' ')
  // If no space found or space is too early, just cut at maxLength
  if (lastSpace === -1 || lastSpace < maxLength * 0.7) {
    return `${truncated}...`
  }
  return `${truncated.slice(0, lastSpace)}...`
}

// Date range presets
const DATE_RANGES = {
  all: { label: 'All time', filter: () => true },
  today: {
    label: 'Today',
    filter: (date) => {
      const now = new Date()
      const goalDate = new Date(date)
      return goalDate.toDateString() === now.toDateString()
    }
  },
  week: {
    label: 'This week',
    filter: (date) => {
      const now = new Date()
      const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      return new Date(date) >= weekAgo
    }
  },
  month: {
    label: 'This month',
    filter: (date) => {
      const now = new Date()
      const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      return new Date(date) >= monthAgo
    }
  }
}

// Sort options
const SORT_OPTIONS = {
  newest: { label: 'Newest first', sort: (a, b) => new Date(b.created_at) - new Date(a.created_at) },
  oldest: { label: 'Oldest first', sort: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  priority_high: {
    label: 'Priority (high first)',
    sort: (a, b) => {
      const order = { P0: 0, P1: 1, P2: 2, P3: 3 }
      return (order[a.priority] ?? 2) - (order[b.priority] ?? 2)
    }
  },
  priority_low: {
    label: 'Priority (low first)',
    sort: (a, b) => {
      const order = { P0: 0, P1: 1, P2: 2, P3: 3 }
      return (order[b.priority] ?? 2) - (order[a.priority] ?? 2)
    }
  },
  comments: {
    label: 'Most comments',
    sort: (a, b, counts) => (counts[b.goal_id] || 0) - (counts[a.goal_id] || 0)
  },
  unevaluated: {
    label: 'Unevaluated first',
    sort: (a, b) => {
      const order = { no_comments: 0, pending: 1, evaluating: 2, complete: 3 }
      return (order[a.conversation_status] ?? 0) - (order[b.conversation_status] ?? 0)
    }
  }
}

// Conversation status options
const STATUS_OPTIONS = {
  all: { label: 'All statuses' },
  no_comments: { label: 'No comments' },
  pending: { label: 'Pending evaluation' },
  evaluating: { label: 'Evaluating' },
  complete: { label: 'Evaluated' }
}

/**
 * Maps conversation-level status to evaluation status for display.
 *
 * Conversation status is an aggregate across all comments in a goal.
 * Maps to evaluation status values for consistent indicator rendering.
 *
 * Green = all evaluated (goal text + all comments)
 * Red/yellow = some unevaluated items remain
 * Amber = evaluation in progress
 * Gray = no comments yet (nothing to evaluate)
 */
function mapConversationStatusToEvaluation(conversationStatus) {
  switch (conversationStatus) {
    case 'no_comments':
      return 'not_evaluated'
    case 'pending':
      return 'pending'
    case 'evaluating':
      return 'evaluating'
    case 'complete':
      return 'evaluated'
    default:
      return 'not_evaluated'
  }
}

function FilterChip({ label, onRemove }) {
  return (
    <span className="filter-chip">
      {label}
      <button type="button" onClick={onRemove} className="filter-chip-remove">
        <X size={10} />
      </button>
    </span>
  )
}

function GoalCard({ goal, isSelected, onClick, commentCount, onDelete, onArchive, onUnarchive }) {
  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'P0': return 'var(--status-offline)'
      case 'P1': return 'var(--warning)'
      case 'P2': return 'var(--primary)'
      case 'P3': return 'var(--text-muted)'
      default: return 'var(--text-muted)'
    }
  }

  const handleDeleteClick = (e) => {
    e.stopPropagation()
    onDelete?.(goal)
  }

  const handleArchiveClick = (e) => {
    e.stopPropagation()
    if (goal.archived) {
      onUnarchive?.(goal)
    } else {
      onArchive?.(goal)
    }
  }

  // Map conversation status to evaluation status for the indicator
  const evaluationStatus = mapConversationStatusToEvaluation(goal.conversation_status)
  const statusClass = `status-${goal.conversation_status || 'no_comments'}`
  const fullText = goal.title || goal.description || ''

  return (
    <button
      type="button"
      className={`goal-history-card ${isSelected ? 'selected' : ''} ${goal.archived ? 'archived' : ''} ${statusClass}`}
      onClick={onClick}
      title={fullText}
    >
      <div className="goal-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="goal-id-badge" title={`Goal ID: ${goal.goal_id}`}>
            #{goal.goal_id?.slice(-6) || '???'}
          </span>
          <span
            className="goal-priority-badge"
            style={{ background: getPriorityColor(goal.priority) }}
          >
            {goal.priority || 'P2'}
          </span>
          {goal.archived && (
            <span className="goal-archived-badge">Archived</span>
          )}
          <EvaluationStatusIndicator status={evaluationStatus} showLabel />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="goal-card-time">
            <Clock size={12} />
            {formatDate(goal.created_at)}
          </span>
          <button
            type="button"
            className="goal-card-action"
            onClick={handleArchiveClick}
            title={goal.archived ? 'Unarchive goal' : 'Archive goal'}
          >
            {goal.archived ? <ArchiveRestore size={12} /> : <Archive size={12} />}
          </button>
          {!goal.archived && (
            <button
              type="button"
              className="goal-card-action goal-card-delete"
              onClick={handleDeleteClick}
              title="Delete goal"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>
      <div className="goal-card-text">
        {goal.summary || truncateAtWordBoundary(fullText, 80)}
      </div>
      <div className="goal-card-footer">
        <div className="goal-card-footer-left">
          {commentCount > 0 && (
            <span className="goal-card-comments">
              <MessageSquare size={12} />
              {commentCount}
            </span>
          )}
          {goal.created_by_name && (
            <span className="goal-attribution">
              by {goal.created_by_name}
            </span>
          )}
        </div>
        <ChevronRight size={14} className="goal-card-chevron" />
      </div>
    </button>
  )
}

function GoalHistoryPanel({
  goals,
  selectedGoalId,
  onSelectGoal,
  onDeleteGoal,
  onArchiveGoal,
  onUnarchiveGoal,
  goalCommentCounts = {},
  goalProgress = {},
  loading = false,
  showArchived = false,
  onToggleShowArchived
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dateRange, setDateRange] = useState('all')
  const [sortBy, setSortBy] = useState('newest')
  const [showFilters, setShowFilters] = useState(false)

  const clearAllFilters = useCallback(() => {
    setSearchQuery('')
    setPriorityFilter('')
    setStatusFilter('')
    setDateRange('all')
    setSortBy('newest')
    if (showArchived && onToggleShowArchived) {
      onToggleShowArchived()
    }
  }, [showArchived, onToggleShowArchived])

  const filteredAndSortedGoals = useMemo(() => {
    let result = goals || []

    // Text search
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      result = result.filter(
        (goal) =>
          goal.title?.toLowerCase().includes(query) ||
          goal.description?.toLowerCase().includes(query) ||
          goal.summary?.toLowerCase().includes(query)
      )
    }

    // Priority filter
    if (priorityFilter) {
      result = result.filter((goal) => goal.priority === priorityFilter)
    }

    // Status filter
    if (statusFilter) {
      result = result.filter((goal) => goal.conversation_status === statusFilter)
    }

    // Date range filter
    if (dateRange !== 'all' && DATE_RANGES[dateRange]) {
      result = result.filter((goal) => DATE_RANGES[dateRange].filter(goal.created_at))
    }

    // Sort
    const sortOption = SORT_OPTIONS[sortBy] || SORT_OPTIONS.newest
    return [...result].sort((a, b) => sortOption.sort(a, b, goalCommentCounts))
  }, [goals, searchQuery, priorityFilter, statusFilter, dateRange, sortBy, goalCommentCounts])

  const hasActiveFilters = searchQuery.trim() || priorityFilter || statusFilter || dateRange !== 'all' || showArchived

  // Build active filter chips
  const activeFilterChips = useMemo(() => {
    const chips = []
    if (priorityFilter) {
      chips.push({ key: 'priority', label: priorityFilter, onRemove: () => setPriorityFilter('') })
    }
    if (statusFilter) {
      chips.push({
        key: 'status',
        label: STATUS_OPTIONS[statusFilter]?.label || statusFilter,
        onRemove: () => setStatusFilter('')
      })
    }
    if (dateRange !== 'all') {
      chips.push({
        key: 'date',
        label: DATE_RANGES[dateRange]?.label || dateRange,
        onRemove: () => setDateRange('all')
      })
    }
    if (showArchived) {
      chips.push({
        key: 'archived',
        label: 'Archived',
        onRemove: onToggleShowArchived
      })
    }
    return chips
  }, [priorityFilter, statusFilter, dateRange, showArchived, onToggleShowArchived])

  return (
    <div className="goal-history-panel">
      <div className="history-panel-header">
        <h3 className="history-panel-title">History</h3>
        <span className="history-panel-count">
          {filteredAndSortedGoals.length}
          {hasActiveFilters && ` / ${goals?.length || 0}`} items
        </span>
      </div>

      <div className="history-panel-search">
        <div className="search-input-wrapper">
          <Search size={14} className="search-icon" />
          <input
            type="text"
            placeholder="Search history..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
          {searchQuery && (
            <button
              type="button"
              className="search-clear"
              onClick={() => setSearchQuery('')}
            >
              <X size={12} />
            </button>
          )}
        </div>
        <button
          type="button"
          className={`filter-toggle ${showFilters || hasActiveFilters ? 'active' : ''}`}
          onClick={() => setShowFilters(!showFilters)}
          title="Filter goals"
        >
          <Filter size={14} />
          {hasActiveFilters && <span className="filter-badge">{activeFilterChips.length}</span>}
        </button>
      </div>

      {showFilters && (
        <div className="history-panel-filters">
          <div className="filter-row">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="filter-select"
            >
              {Object.entries(STATUS_OPTIONS).map(([value, { label }]) => (
                <option key={value} value={value === 'all' ? '' : value}>
                  {label}
                </option>
              ))}
            </select>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="filter-select"
            >
              <option value="">All priorities</option>
              <option value="P0">P0 - Critical</option>
              <option value="P1">P1 - High</option>
              <option value="P2">P2 - Medium</option>
              <option value="P3">P3 - Low</option>
            </select>
          </div>
          <div className="filter-row">
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="filter-select"
            >
              {Object.entries(DATE_RANGES).map(([value, { label }]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <div className="sort-wrapper">
              <ArrowUpDown size={12} className="sort-icon" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="filter-select sort-select"
              >
                {Object.entries(SORT_OPTIONS).map(([value, { label }]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="filter-row filter-row-options">
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={onToggleShowArchived}
              />
              <Archive size={12} />
              Show Archived
            </label>
          </div>
          {hasActiveFilters && (
            <button
              type="button"
              className="clear-filters"
              onClick={clearAllFilters}
            >
              Clear all filters
            </button>
          )}
        </div>
      )}

      {activeFilterChips.length > 0 && (
        <div className="active-filters-bar">
          {activeFilterChips.map((chip) => (
            <FilterChip key={chip.key} label={chip.label} onRemove={chip.onRemove} />
          ))}
        </div>
      )}

      <div className="history-panel-list">
        {loading ? (
          <div className="history-panel-empty">Loading...</div>
        ) : filteredAndSortedGoals.length === 0 ? (
          <div className="history-panel-empty">
            {hasActiveFilters
              ? 'No items match your filters'
              : 'No directives yet. Start a conversation to create one.'}
          </div>
        ) : (
          filteredAndSortedGoals.map((goal) => (
            <GoalCard
              key={goal.goal_id}
              goal={goal}
              isSelected={selectedGoalId === goal.goal_id}
              onClick={() => onSelectGoal(goal)}
              onDelete={onDeleteGoal}
              onArchive={onArchiveGoal}
              onUnarchive={onUnarchiveGoal}
              commentCount={goalCommentCounts[goal.goal_id] || 0}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default GoalHistoryPanel
