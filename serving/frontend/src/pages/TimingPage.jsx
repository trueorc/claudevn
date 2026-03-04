import { useState, useMemo } from 'react'
import { RefreshCw, Clock, BarChart3, Timer, ChevronDown, ChevronRight, Layers, AlertCircle, FolderOpen } from 'lucide-react'
import Spinner from '../components/common/Spinner'
import EmptyState from '../components/common/EmptyState'
import { useProjectContext } from '../contexts/ProjectContext'
import useTiming from '../hooks/useTiming'
import './TimingPage.css'

const PHASE_LABELS = {
  workspace_setup: 'Workspace Setup',
  repo_clone: 'Repo Clone',
  sdk_launch: 'SDK Launch',
  mcp_tool_call: 'MCP Tool Call',
  tool_use: 'Tool Use',
  api_inference: 'API Inference',
  sdk_execution: 'SDK Execution',
  git_push: 'Git Push',
  total_wall_time: 'Total Wall Time'
}

const PHASE_COLORS = {
  workspace_setup: '#3b82f6',
  repo_clone: '#8b5cf6',
  sdk_launch: '#f59e0b',
  mcp_tool_call: '#10b981',
  tool_use: '#14b8a6',
  api_inference: '#ef4444',
  sdk_execution: '#f97316',
  git_push: '#6366f1',
  total_wall_time: '#64748b'
}

const PHASE_BG_COLORS = {
  workspace_setup: 'rgba(59, 130, 246, 0.15)',
  repo_clone: 'rgba(139, 92, 246, 0.15)',
  sdk_launch: 'rgba(245, 158, 11, 0.15)',
  mcp_tool_call: 'rgba(16, 185, 129, 0.15)',
  tool_use: 'rgba(20, 184, 166, 0.15)',
  api_inference: 'rgba(239, 68, 68, 0.15)',
  sdk_execution: 'rgba(249, 115, 22, 0.15)',
  git_push: 'rgba(99, 102, 241, 0.15)',
  total_wall_time: 'rgba(100, 116, 139, 0.15)'
}

const LONG_RUNNING_THRESHOLD_MS = 90000

function formatDuration(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

function formatTimestamp(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleTimeString()
}

function formatTokens(n) {
  if (n == null || n === 0) return null
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`
  return `${n}`
}

function formatCost(usd) {
  if (usd == null || usd === 0) return null
  return `$${usd.toFixed(2)}`
}

/** Strip common prefixes from MCP tool names (e.g. "claudevn_get_context" -> "get_context") */
function cleanToolName(name) {
  if (!name) return name
  return name.replace(/^claudevn_/, '')
}

/** Check if an entry's metadata indicates it's an MCP tool call */
function isMcpEntry(entry) {
  if (entry.phase === 'mcp_tool_call') return true
  const meta = entry.metadata || {}
  return meta.tool_name?.startsWith('claudevn_') || false
}

/** Get display name for an entry */
function getEntryDisplayName(entry) {
  const meta = entry.metadata || {}
  if (meta.tool_name) return cleanToolName(meta.tool_name)
  return PHASE_LABELS[entry.phase] || entry.phase
}

/** Sum all entry durations for a list of work items (excluding total_wall_time) */
function sumEntryDurations(items) {
  return items.reduce((sum, item) => {
    return sum + item.entries
      .filter(e => e.duration_ms != null && e.phase !== 'total_wall_time')
      .reduce((s, e) => s + (e.duration_ms || 0), 0)
  }, 0)
}

function PhasePill({ phase, toolName }) {
  const color = PHASE_COLORS[phase] || '#94a3b8'
  const bgColor = PHASE_BG_COLORS[phase] || 'rgba(148, 163, 184, 0.15)'
  const label = toolName || PHASE_LABELS[phase] || phase

  return (
    <span className="phase-pill" style={{ backgroundColor: bgColor, color }}>
      <span className="phase-dot" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

function AggregateStatsTable({ aggregates }) {
  if (!aggregates.length) {
    return <p className="timing-empty">No aggregate data yet</p>
  }

  const maxAvg = Math.max(...aggregates.map(s => s.avg_ms))

  return (
    <div className="timing-table-container">
      <table className="timing-table">
        <thead>
          <tr>
            <th>Phase</th>
            <th>Count</th>
            <th>Avg</th>
            <th>P50</th>
            <th>P95</th>
            <th>P99</th>
            <th>Min</th>
            <th>Max</th>
          </tr>
        </thead>
        <tbody>
          {aggregates.map(stat => {
            const key = stat.tool_name
              ? `${stat.phase}:${stat.tool_name}`
              : stat.phase
            return (
              <tr key={key}>
                <td><PhasePill phase={stat.phase} toolName={stat.tool_name} /></td>
                <td className="timing-num">{stat.count}</td>
                <td className="timing-num">
                  <div className="stat-bar-container">
                    <span>{formatDuration(stat.avg_ms)}</span>
                    <span
                      className="stat-bar"
                      style={{
                        width: `${Math.max((stat.avg_ms / maxAvg) * 60, 3)}px`,
                        backgroundColor: PHASE_COLORS[stat.phase] || '#94a3b8',
                        opacity: 0.6
                      }}
                    />
                  </div>
                </td>
                <td className="timing-num">{formatDuration(stat.p50_ms)}</td>
                <td className="timing-num">{formatDuration(stat.p95_ms)}</td>
                <td className="timing-num">{formatDuration(stat.p99_ms)}</td>
                <td className="timing-num">{formatDuration(stat.min_ms)}</td>
                <td className="timing-num">{formatDuration(stat.max_ms)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ProjectSummary({ workItems, totalWorkItems }) {
  // Sum all entry durations (excluding total_wall_time) across all work items
  const totalDuration = sumEntryDurations(workItems)

  const issueCount = new Set(
    workItems.filter(i => i.issue_id).map(i => i.issue_id)
  ).size

  const totalTokens = workItems.reduce((sum, item) => {
    return sum + (item.input_tokens || 0) + (item.output_tokens || 0)
  }, 0)

  const totalCost = workItems.reduce((sum, item) => {
    return sum + (item.total_cost_usd || 0)
  }, 0)

  const tokensFormatted = formatTokens(totalTokens)
  const costFormatted = formatCost(totalCost)

  return (
    <div className="timing-project-summary">
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Total Time</span>
        <span className="timing-project-stat-value accent">{formatDuration(totalDuration)}</span>
      </div>
      <div className="timing-project-divider" />
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Issues</span>
        <span className="timing-project-stat-value">{issueCount}</span>
      </div>
      <div className="timing-project-divider" />
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Work Items</span>
        <span className="timing-project-stat-value">{totalWorkItems}</span>
      </div>
      {tokensFormatted && (
        <>
          <div className="timing-project-divider" />
          <div className="timing-project-stat">
            <span className="timing-project-stat-label">Tokens</span>
            <span className="timing-project-stat-value">{tokensFormatted}</span>
          </div>
        </>
      )}
      {costFormatted && (
        <>
          <div className="timing-project-divider" />
          <div className="timing-project-stat">
            <span className="timing-project-stat-label">Cost</span>
            <span className="timing-project-stat-value">{costFormatted}</span>
          </div>
        </>
      )}
    </div>
  )
}

function ToolCallRow({ entry, maxDuration }) {
  const displayName = getEntryDisplayName(entry)
  const mcp = isMcpEntry(entry)
  const duration = entry.duration_ms || 0
  const isLong = duration >= LONG_RUNNING_THRESHOLD_MS
  const barPercent = maxDuration > 0 ? Math.min((duration / maxDuration) * 100, 100) : 0
  const color = isLong ? '#ef4444' : (PHASE_COLORS[entry.phase] || '#94a3b8')

  const meta = entry.metadata || {}
  const metaEntries = Object.entries(meta).filter(([k]) => k !== 'tool_name')

  return (
    <>
      <div className="tool-call-row">
        <div className="tool-call-name">
          <span className="tool-call-label">{displayName}</span>
          {mcp && <span className="tool-call-badge mcp">MCP</span>}
          {!mcp && entry.phase !== 'total_wall_time' && (
            <span className="tool-call-badge phase">{PHASE_LABELS[entry.phase] || entry.phase}</span>
          )}
        </div>
        <div className="tool-call-duration-bar">
          <div className="duration-bar-track">
            <div
              className="duration-bar-fill"
              style={{
                width: `${Math.max(barPercent, 1)}%`,
                backgroundColor: color
              }}
            />
          </div>
        </div>
        <span className={`tool-call-duration${isLong ? ' long-running' : ''}`}>
          {formatDuration(duration)}
        </span>
      </div>
      {metaEntries.length > 0 && (
        <div className="tool-call-row" style={{ paddingTop: 0 }}>
          <span className="tool-call-meta">
            {metaEntries.map(([k, v]) => `${k}=${v}`).join(', ')}
          </span>
        </div>
      )}
    </>
  )
}

function WorkItemGroup({ groupKey, label, sublabel, items }) {
  const [expanded, setExpanded] = useState(false)

  const allEntries = items.flatMap(item =>
    item.entries.filter(e => e.duration_ms != null && e.phase !== 'total_wall_time')
  )

  const totalDuration = allEntries.reduce((sum, e) => sum + (e.duration_ms || 0), 0)
  const maxEntryDuration = allEntries.length > 0
    ? Math.max(...allEntries.map(e => e.duration_ms || 0))
    : 1

  const latestTime = items.length > 0
    ? items.reduce((latest, item) => {
        const t = new Date(item.created_at).getTime()
        return t > latest ? t : latest
      }, 0)
    : null

  const groupTokens = items.reduce((sum, item) => {
    return sum + (item.input_tokens || 0) + (item.output_tokens || 0)
  }, 0)

  const groupCost = items.reduce((sum, item) => {
    return sum + (item.total_cost_usd || 0)
  }, 0)

  const groupTokensFormatted = formatTokens(groupTokens)
  const groupCostFormatted = formatCost(groupCost)

  return (
    <div className="issue-group">
      <div className="issue-group-header" onClick={() => setExpanded(!expanded)}>
        <span className="issue-group-expand">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <div className="issue-group-primary">
          <span className="issue-group-title">{label}</span>
          {sublabel && <span className="issue-group-subtitle">{sublabel}</span>}
        </div>
        <div className="issue-group-stats">
          <span className="issue-group-calls">{allEntries.length} calls</span>
          <span className="issue-group-duration">{formatDuration(totalDuration)}</span>
          {groupTokensFormatted && (
            <span className="issue-group-tokens">{groupTokensFormatted}</span>
          )}
          {groupCostFormatted && (
            <span className="issue-group-cost">{groupCostFormatted}</span>
          )}
          {latestTime && (
            <span className="issue-group-time">{formatTimestamp(new Date(latestTime).toISOString())}</span>
          )}
        </div>
      </div>
      {expanded && (
        <div className="issue-group-detail">
          <div className="tool-call-list">
            {allEntries.map((entry, idx) => (
              <ToolCallRow key={idx} entry={entry} maxDuration={maxEntryDuration} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Classify work items into three tiers: directives, issues, unassigned */
function classifyWorkItems(workItems) {
  const directiveGroups = new Map()
  const issueGroups = new Map()
  const unassigned = []

  for (const item of workItems) {
    if (item.issue_id) {
      // Issue tier: has a resolved issue
      const key = item.issue_id
      if (!issueGroups.has(key)) {
        issueGroups.set(key, {
          key,
          label: item.issue_title || item.issue_id,
          sublabel: item.issue_id,
          items: []
        })
      }
      const group = issueGroups.get(key)
      if (item.issue_title && !group.label) {
        group.label = item.issue_title
      }
      group.items.push(item)
    } else if (item.directive_id) {
      // Directive tier: decomp, char, conflict, compute lifecycle
      const key = item.directive_id
      if (!directiveGroups.has(key)) {
        directiveGroups.set(key, {
          key,
          label: item.directive_title || item.directive_id,
          sublabel: item.work_id,
          items: []
        })
      }
      directiveGroups.get(key).items.push(item)
    } else {
      // Unassigned: not linked to directive or issue
      unassigned.push(item)
    }
  }

  // Sort each tier by most recent item
  const sortByRecent = (groups) =>
    [...groups.values()].sort((a, b) => {
      const aTime = Math.max(...a.items.map(i => new Date(i.created_at).getTime()))
      const bTime = Math.max(...b.items.map(i => new Date(i.created_at).getTime()))
      return bTime - aTime
    })

  // Unassigned: each work item is its own group
  const unassignedGroups = unassigned.map(item => ({
    key: item.work_id,
    label: item.work_id,
    sublabel: null,
    items: [item]
  }))

  return {
    directives: sortByRecent(directiveGroups),
    issues: sortByRecent(issueGroups),
    unassigned: unassignedGroups
  }
}

function TimingPage() {
  const { activeProject } = useProjectContext()
  const activeProjectId = activeProject?.project_id || null

  const { workItems, aggregates, totalWorkItems, loading, error, refresh } = useTiming(activeProjectId, {
    pollInterval: 10000,
    limit: 20
  })

  const { directives, issues, unassigned } = useMemo(
    () => classifyWorkItems(workItems),
    [workItems]
  )

  if (!activeProjectId) {
    return (
      <div className="page">
        <header className="page-header">
          <h1 className="page-title">
            <Timer size={20} />
            Timing
          </h1>
        </header>
        <EmptyState
          icon={FolderOpen}
          title="Select a Project"
          description="Please select a project from the sidebar to view timing data."
        />
      </div>
    )
  }

  if (loading && !workItems.length) {
    return (
      <div className="page">
        <header className="page-header">
          <h1 className="page-title">Timing</h1>
        </header>
        <div className="loading-container">
          <Spinner />
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-content">
          <h1 className="page-title">
            <Timer size={20} />
            Timing
          </h1>
        </div>
        <button onClick={refresh} className="refresh-btn" disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Project Summary */}
      <ProjectSummary workItems={workItems} totalWorkItems={totalWorkItems} />

      {/* Aggregate Stats Section */}
      <section className="timing-section">
        <header className="section-header">
          <h2 className="section-title">
            <BarChart3 size={16} />
            Aggregate Statistics
          </h2>
        </header>
        <AggregateStatsTable aggregates={aggregates} />
      </section>

      {/* Directives Section */}
      {directives.length > 0 && (
        <section className="timing-section">
          <header className="section-header">
            <h2 className="section-title">
              <Layers size={16} />
              Directives
            </h2>
          </header>
          <div className="issue-groups-list">
            {directives.map(group => (
              <WorkItemGroup
                key={group.key}
                groupKey={group.key}
                label={group.label}
                sublabel={group.sublabel}
                items={group.items}
              />
            ))}
          </div>
        </section>
      )}

      {/* Issues Section */}
      <section className="timing-section">
        <header className="section-header">
          <h2 className="section-title">
            <Clock size={16} />
            Issues
          </h2>
        </header>
        {issues.length === 0 ? (
          <p className="timing-empty">No issue timing data yet. Timing data will appear when compute instances process work items.</p>
        ) : (
          <div className="issue-groups-list">
            {issues.map(group => (
              <WorkItemGroup
                key={group.key}
                groupKey={group.key}
                label={group.label}
                sublabel={group.sublabel}
                items={group.items}
              />
            ))}
          </div>
        )}
      </section>

      {/* Unassigned Section */}
      {unassigned.length > 0 && (
        <section className="timing-section">
          <header className="section-header">
            <h2 className="section-title">
              <AlertCircle size={16} />
              Unassigned
            </h2>
          </header>
          <div className="issue-groups-list">
            {unassigned.map(group => (
              <WorkItemGroup
                key={group.key}
                groupKey={group.key}
                label={group.label}
                sublabel={group.sublabel}
                items={group.items}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

export default TimingPage
export { formatDuration, cleanToolName, classifyWorkItems, sumEntryDurations, formatTokens, formatCost, LONG_RUNNING_THRESHOLD_MS }
