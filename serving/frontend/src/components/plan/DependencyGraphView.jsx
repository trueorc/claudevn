import { useState, useMemo, useEffect } from 'react'
import { ChevronDown, ChevronRight, Target } from 'lucide-react'
import { getGoals } from '../../api/workmap'
import { useProjectContext } from '../../contexts/ProjectContext'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'

function getStatusClass(status) {
  switch (status?.toLowerCase()) {
    case 'done':
    case 'completed':
      return 'directive-chip--done'
    case 'in_progress':
    case 'in_review':
      return 'directive-chip--progress'
    case 'ready':
      return 'directive-chip--ready'
    case 'blocked':
      return 'directive-chip--blocked'
    default:
      return 'directive-chip--backlog'
  }
}

function getStatusSortOrder(status) {
  switch (status?.toLowerCase()) {
    case 'blocked': return 0
    case 'in_progress':
    case 'in_review': return 1
    case 'ready': return 2
    case 'backlog': return 3
    case 'done':
    case 'completed': return 4
    default: return 5
  }
}

function DirectiveSection({ directive, issues, expanded, onToggle }) {
  const statusCounts = useMemo(() => {
    const counts = { done: 0, progress: 0, ready: 0, blocked: 0, backlog: 0 }
    for (const issue of issues) {
      const s = issue.status?.toLowerCase()
      if (s === 'done' || s === 'completed') counts.done++
      else if (s === 'in_progress' || s === 'in_review') counts.progress++
      else if (s === 'ready') counts.ready++
      else if (s === 'blocked') counts.blocked++
      else counts.backlog++
    }
    return counts
  }, [issues])

  const sortedIssues = useMemo(() => {
    return [...issues].sort((a, b) => getStatusSortOrder(a.status) - getStatusSortOrder(b.status))
  }, [issues])

  return (
    <div className="directive-section">
      <button className="directive-header" onClick={onToggle}>
        <span className="directive-chevron">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="directive-name">
          {directive.name || `Directive ${directive.goal_id.slice(0, 8)}`}
        </span>
        <span className="directive-issue-count">
          {issues.length} issue{issues.length !== 1 ? 's' : ''}
        </span>
        <span className="directive-status-dots">
          {statusCounts.blocked > 0 && (
            <span className="directive-dot directive-dot--blocked" title={`${statusCounts.blocked} blocked`}>
              {statusCounts.blocked}
            </span>
          )}
          {statusCounts.progress > 0 && (
            <span className="directive-dot directive-dot--progress" title={`${statusCounts.progress} in progress`}>
              {statusCounts.progress}
            </span>
          )}
          {statusCounts.ready > 0 && (
            <span className="directive-dot directive-dot--ready" title={`${statusCounts.ready} ready`}>
              {statusCounts.ready}
            </span>
          )}
          {statusCounts.backlog > 0 && (
            <span className="directive-dot directive-dot--backlog" title={`${statusCounts.backlog} backlog`}>
              {statusCounts.backlog}
            </span>
          )}
          {statusCounts.done > 0 && (
            <span className="directive-dot directive-dot--done" title={`${statusCounts.done} done`}>
              {statusCounts.done}
            </span>
          )}
        </span>
      </button>
      {expanded && (
        <div className="directive-issues">
          <div className="directive-issues-grid">
            {sortedIssues.map(issue => (
              <span
                key={issue.issue_id}
                className={`directive-chip ${getStatusClass(issue.status)}`}
                title={`#${issue.number || issue.issue_id} ${issue.title} (${issue.status})`}
              >
                <span className="directive-chip-number">#{issue.number || '?'}</span>
                <span className="directive-chip-title">{issue.title}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function DependencyGraphView({ data, loading }) {
  const { activeProject } = useProjectContext()
  const [expandedMap, setExpandedMap] = useState({})
  const [goals, setGoals] = useState([])
  const [goalsLoading, setGoalsLoading] = useState(false)

  useEffect(() => {
    async function fetchGoals() {
      if (!activeProject?.project_id) return
      setGoalsLoading(true)
      try {
        const result = await getGoals(false, activeProject.project_id)
        setGoals(result)
      } catch {
        // Goals are optional - sections show fallback names
      } finally {
        setGoalsLoading(false)
      }
    }
    fetchGoals()
  }, [activeProject?.project_id])

  const directives = useMemo(() => {
    if (!data) return []

    const allItems = [
      ...(data.running_items || []),
      ...(data.queued_items || []),
      ...(data.blocked_items || []),
      ...(data.backlog_items || []),
      ...(data.failed_items || []),
      ...(data.done_items || []),
    ]

    if (allItems.length === 0) return []

    const goalMap = {}
    for (const g of goals) {
      goalMap[g.goal_id] = g
    }

    const groups = {}
    for (const item of allItems) {
      const gid = item.goal_id || '__ungrouped__'
      if (!groups[gid]) {
        groups[gid] = {
          goal_id: gid,
          name: gid === '__ungrouped__'
            ? 'Ungrouped Issues'
            : (goalMap[gid]?.name || goalMap[gid]?.title || null),
          issues: [],
        }
      }
      groups[gid].issues.push(item)
    }

    return Object.values(groups).sort((a, b) => {
      if (a.goal_id === '__ungrouped__') return 1
      if (b.goal_id === '__ungrouped__') return -1

      const hasActive = (items) => items.some(i =>
        ['in_progress', 'in_review', 'blocked', 'ready'].includes(i.status?.toLowerCase())
      )
      const aActive = hasActive(a.issues)
      const bActive = hasActive(b.issues)
      if (aActive && !bActive) return -1
      if (!aActive && bActive) return 1
      return b.issues.length - a.issues.length
    })
  }, [data, goals])

  const toggleDirective = (goalId) => {
    setExpandedMap(prev => ({ ...prev, [goalId]: !prev[goalId] }))
  }

  const allExpanded = directives.length > 0 && directives.every(d => expandedMap[d.goal_id])

  const toggleAll = () => {
    if (allExpanded) {
      setExpandedMap({})
    } else {
      const map = {}
      for (const d of directives) map[d.goal_id] = true
      setExpandedMap(map)
    }
  }

  if (loading || goalsLoading) {
    return (
      <div className="plan-loading-state">
        <Spinner />
      </div>
    )
  }

  if (directives.length === 0) {
    return (
      <EmptyState
        icon={Target}
        title="No directives"
        description="Issues grouped by directive will appear here"
      />
    )
  }

  return (
    <div className="directive-view">
      <div className="directive-toolbar">
        <button className="directive-toggle-all" onClick={toggleAll}>
          {allExpanded ? 'Collapse All' : 'Expand All'}
        </button>
      </div>
      <div className="directive-list">
        {directives.map(d => (
          <DirectiveSection
            key={d.goal_id}
            directive={d}
            issues={d.issues}
            expanded={!!expandedMap[d.goal_id]}
            onToggle={() => toggleDirective(d.goal_id)}
          />
        ))}
      </div>
    </div>
  )
}

export default DependencyGraphView
