import { useState, useCallback, useEffect } from 'react'
import { ChevronDown, ChevronRight, Target, AlertCircle, GripVertical, Plus, Calendar } from 'lucide-react'
import { StatusBadge } from '../common/Badge'
import Badge from '../common/Badge'
import EmptyState from '../common/EmptyState'
import Spinner from '../common/Spinner'
import IssueFormModal from './IssueFormModal'
import IssueDetailModal from './IssueDetailModal'
import { updateIssuePriority, updateIssueStatus, getReleases } from '../../api/workmap'
import './WorkMapBacklog.css'

const priorityColors = {
  P0: 'error',
  P1: 'warning',
  P2: 'default',
  P3: 'info'
}

const priorityOrder = ['P0', 'P1', 'P2', 'P3']

const statusOptions = [
  { value: 'backlog', label: 'Backlog', short: 'BL' },
  { value: 'ready', label: 'Ready', short: 'RD' },
  { value: 'in_progress', label: 'In Progress', short: 'IP' },
  { value: 'blocked', label: 'Blocked', short: 'BK' },
  { value: 'done', label: 'Done', short: 'DN' }
]

function WorkMapBacklog({ issuesByGoal, loading, filters, onFilterChange, onIssueUpdate }) {
  const [expandedGoals, setExpandedGoals] = useState(new Set())
  const [draggedIssue, setDraggedIssue] = useState(null)
  const [dropTarget, setDropTarget] = useState(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editingIssue, setEditingIssue] = useState(null)
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [statusUpdating, setStatusUpdating] = useState(null)
  const [releases, setReleases] = useState([])

  useEffect(() => {
    const loadReleases = async () => {
      try {
        const data = await getReleases()
        setReleases(data?.items || [])
      } catch (err) {
        console.error('Failed to load releases:', err)
      }
    }
    loadReleases()
  }, [])

  const toggleGoal = (goalId) => {
    setExpandedGoals(prev => {
      const next = new Set(prev)
      if (next.has(goalId)) {
        next.delete(goalId)
      } else {
        next.add(goalId)
      }
      return next
    })
  }

  const expandAll = () => {
    setExpandedGoals(new Set(issuesByGoal.map(g => g.goal_id || 'no-goal')))
  }

  const collapseAll = () => {
    setExpandedGoals(new Set())
  }

  const handleDragStart = useCallback((e, issue) => {
    setDraggedIssue(issue)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', issue.id || issue.issue_id)
    setTimeout(() => {
      e.target.classList.add('dragging')
    }, 0)
  }, [])

  const handleDragEnd = useCallback((e) => {
    e.target.classList.remove('dragging')
    setDraggedIssue(null)
    setDropTarget(null)
  }, [])

  const handleDragOver = useCallback((e, priority) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDropTarget(priority)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDropTarget(null)
  }, [])

  const handleDrop = useCallback(async (e, targetPriority) => {
    e.preventDefault()
    setDropTarget(null)

    if (!draggedIssue || draggedIssue.priority === targetPriority) {
      return
    }

    try {
      const issueId = draggedIssue.issue_id || draggedIssue.id
      await updateIssuePriority(issueId, targetPriority)
      if (onIssueUpdate) {
        onIssueUpdate()
      }
    } catch (error) {
      console.error('Failed to update issue priority:', error)
    }
  }, [draggedIssue, onIssueUpdate])

  const handleStatusChange = useCallback(async (e, issue, newStatus) => {
    e.stopPropagation()
    if (issue.status === newStatus) return

    const issueId = issue.issue_id || issue.id
    setStatusUpdating(issueId)

    try {
      await updateIssueStatus(issueId, newStatus)
      if (onIssueUpdate) {
        onIssueUpdate()
      }
    } catch (error) {
      console.error('Failed to update issue status:', error)
    } finally {
      setStatusUpdating(null)
    }
  }, [onIssueUpdate])

  const handleIssueClick = useCallback((e, issue) => {
    // Don't open modal if clicking on drag handle or status dropdown
    if (e.target.closest('.drag-handle') || e.target.closest('.status-quick-select')) {
      return
    }
    setSelectedIssue(issue)
  }, [])

  const handleEditFromDetail = useCallback((issue) => {
    setSelectedIssue(null)
    setEditingIssue(issue)
  }, [])

  const handleFormSuccess = useCallback(() => {
    setCreateModalOpen(false)
    setEditingIssue(null)
    if (onIssueUpdate) {
      onIssueUpdate()
    }
  }, [onIssueUpdate])

  const handleDetailSuccess = useCallback(() => {
    if (onIssueUpdate) {
      onIssueUpdate()
    }
  }, [onIssueUpdate])

  if (loading) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  const hasIssues = issuesByGoal && issuesByGoal.length > 0

  return (
    <div className="workmap-backlog">
      <div className="backlog-header">
        <div className="backlog-filters">
          <select
            value={filters?.status || 'all'}
            onChange={(e) => onFilterChange({ ...filters, status: e.target.value === 'all' ? null : e.target.value })}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="backlog">Backlog</option>
            <option value="ready">Ready</option>
            <option value="in_progress">In Progress</option>
            <option value="in_review">In Review</option>
            <option value="blocked">Blocked</option>
            <option value="done">Done</option>
          </select>

          <select
            value={filters?.priority || 'all'}
            onChange={(e) => onFilterChange({ ...filters, priority: e.target.value === 'all' ? null : e.target.value })}
            className="filter-select"
          >
            <option value="all">All Priorities</option>
            <option value="P0">P0</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>

          <select
            value={filters?.release_id || 'all'}
            onChange={(e) => onFilterChange({ ...filters, release_id: e.target.value === 'all' ? null : e.target.value })}
            className="filter-select"
          >
            <option value="all">All Releases</option>
            <option value="unscheduled">Unscheduled</option>
            {releases.map(release => (
              <option key={release.release_id} value={release.release_id}>
                {release.name}
              </option>
            ))}
          </select>
        </div>

        <div className="backlog-actions">
          <button onClick={() => setCreateModalOpen(true)} className="action-btn create-btn">
            <Plus size={14} />
            Create Issue
          </button>
          <button onClick={expandAll} className="action-btn">
            Expand All
          </button>
          <button onClick={collapseAll} className="action-btn">
            Collapse All
          </button>
        </div>
      </div>

      {!hasIssues ? (
        <EmptyState
          icon={Target}
          title="No issues found"
          description="Create an issue or use goal decomposition to generate issues"
          action={
            <button onClick={() => setCreateModalOpen(true)} className="btn btn-primary">
              <Plus size={14} />
              Create Issue
            </button>
          }
        />
      ) : (
        <div className="goals-list">
          {issuesByGoal.map(goal => {
            const goalId = goal.goal_id || 'no-goal'
            const isExpanded = expandedGoals.has(goalId)
            const issueCount = goal.issues?.length || 0

            return (
              <div key={goalId} className="goal-section">
                <button
                  onClick={() => toggleGoal(goalId)}
                  className="goal-header"
                >
                  <div className="goal-toggle">
                    {isExpanded ? (
                      <ChevronDown size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </div>
                  <div className="goal-info">
                    <div className="goal-title">
                      <Target size={14} />
                      <span>{goal.goal_name || goal.title || 'No Goal'}</span>
                    </div>
                    {goal.goal_description && (
                      <p className="goal-description">{goal.goal_description}</p>
                    )}
                  </div>
                  <div className="goal-count">
                    {issueCount} {issueCount === 1 ? 'issue' : 'issues'}
                  </div>
                </button>

                {isExpanded && (
                  <div className="issues-container">
                    <div className="priority-drop-zones">
                      {priorityOrder.map(priority => (
                        <div
                          key={priority}
                          className={`priority-drop-zone ${dropTarget === priority ? 'drop-target-active' : ''}`}
                          onDragOver={(e) => handleDragOver(e, priority)}
                          onDragLeave={handleDragLeave}
                          onDrop={(e) => handleDrop(e, priority)}
                        >
                          <Badge variant={priorityColors[priority]}>{priority}</Badge>
                          <span className="drop-hint">Drop to set {priority}</span>
                        </div>
                      ))}
                    </div>
                    <div className="issues-list">
                      {goal.issues && goal.issues.length > 0 ? (
                        goal.issues.map(issue => {
                          const issueId = issue.issue_id || issue.id
                          const isUpdating = statusUpdating === issueId

                          return (
                            <div
                              key={issueId}
                              className={`issue-card ${draggedIssue?.id === issueId || draggedIssue?.issue_id === issueId ? 'dragging' : ''} clickable`}
                              draggable
                              onDragStart={(e) => handleDragStart(e, issue)}
                              onDragEnd={handleDragEnd}
                              onClick={(e) => handleIssueClick(e, issue)}
                            >
                              <div className="drag-handle">
                                <GripVertical size={14} />
                              </div>
                              <div className="issue-content">
                                <div className="issue-header">
                                  <div className="issue-id">#{issue.number || issueId}</div>
                                  <h4 className="issue-title">{issue.title}</h4>
                                </div>

                                <div className="issue-badges">
                                  <StatusBadge status={issue.status} />
                                  {issue.priority && (
                                    <Badge variant={priorityColors[issue.priority] || 'default'}>
                                      {issue.priority}
                                    </Badge>
                                  )}
                                  {issue.size && (
                                    <Badge variant="default">{issue.size}</Badge>
                                  )}
                                  {issue.release_id && (
                                    <Badge variant="info">
                                      <Calendar size={10} style={{ marginRight: '4px' }} />
                                      {issue.release_name || releases.find(r => r.release_id === issue.release_id)?.name || issue.release_id}
                                    </Badge>
                                  )}
                                </div>

                                <div className="issue-status-row">
                                  <select
                                    className="status-quick-select"
                                    value={issue.status}
                                    onChange={(e) => handleStatusChange(e, issue, e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                    disabled={isUpdating}
                                  >
                                    {statusOptions.map(opt => (
                                      <option key={opt.value} value={opt.value}>
                                        {opt.label}
                                      </option>
                                    ))}
                                  </select>
                                </div>

                                {issue.dependencies && issue.dependencies.length > 0 && (
                                  <div className="issue-dependencies">
                                    <span className="dep-label">Depends on:</span>
                                    <div className="dep-list">
                                      {issue.dependencies.map(dep => (
                                        <span key={dep} className="dep-item">#{dep}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {issue.depends_on && issue.depends_on.length > 0 && (
                                  <div className="issue-dependencies">
                                    <span className="dep-label">Depends on:</span>
                                    <div className="dep-list">
                                      {issue.depends_on.map(dep => (
                                        <span key={dep} className="dep-item">#{dep}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {issue.blockers && issue.blockers.length > 0 && (
                                  <div className="issue-blockers">
                                    <AlertCircle size={12} />
                                    <span>{issue.blockers.length} blocker{issue.blockers.length !== 1 ? 's' : ''}</span>
                                  </div>
                                )}

                                {issue.labels && issue.labels.length > 0 && (
                                  <div className="issue-labels">
                                    {issue.labels.map(label => {
                                      const isInitiative = label.startsWith('initiative:')
                                      const displayName = isInitiative ? label.slice(11) : label
                                      return (
                                        <span
                                          key={label}
                                          className={isInitiative ? 'label-initiative' : 'issue-label'}
                                          title={label}
                                        >
                                          {displayName}
                                        </span>
                                      )
                                    })}
                                  </div>
                                )}
                              </div>
                            </div>
                          )
                        })
                      ) : (
                        <div className="empty-goal">
                          <span>No issues in this goal</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <IssueFormModal
        isOpen={createModalOpen || Boolean(editingIssue)}
        onClose={() => {
          setCreateModalOpen(false)
          setEditingIssue(null)
        }}
        issue={editingIssue}
        onSuccess={handleFormSuccess}
      />

      <IssueDetailModal
        isOpen={Boolean(selectedIssue)}
        onClose={() => setSelectedIssue(null)}
        issue={selectedIssue}
        onEdit={handleEditFromDetail}
        onSuccess={handleDetailSuccess}
      />
    </div>
  )
}

export default WorkMapBacklog
