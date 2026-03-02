import { useState, useMemo } from 'react'
import { RefreshCw, Clock, BarChart3, Timer, ChevronDown, ChevronRight } from 'lucide-react'
import Spinner from '../components/common/Spinner'
import useTiming from '../hooks/useTiming'
import './TimingPage.css'

const PHASE_LABELS = {
  workspace_setup: 'Workspace Setup',
  repo_clone: 'Repo Clone',
  sdk_launch: 'SDK Launch',
  mcp_tool_call: 'MCP Tool Call',
  api_inference: 'API Inference',
  git_push: 'Git Push',
  total_wall_time: 'Total Wall Time'
}

const PHASE_COLORS = {
  workspace_setup: '#3b82f6',
  repo_clone: '#8b5cf6',
  sdk_launch: '#f59e0b',
  mcp_tool_call: '#10b981',
  api_inference: '#ef4444',
  git_push: '#6366f1',
  total_wall_time: '#64748b'
}

const PHASE_BG_COLORS = {
  workspace_setup: 'rgba(59, 130, 246, 0.15)',
  repo_clone: 'rgba(139, 92, 246, 0.15)',
  sdk_launch: 'rgba(245, 158, 11, 0.15)',
  mcp_tool_call: 'rgba(16, 185, 129, 0.15)',
  api_inference: 'rgba(239, 68, 68, 0.15)',
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

function PhasePill({ phase }) {
  const color = PHASE_COLORS[phase] || '#94a3b8'
  const bgColor = PHASE_BG_COLORS[phase] || 'rgba(148, 163, 184, 0.15)'

  return (
    <span className="phase-pill" style={{ backgroundColor: bgColor, color }}>
      <span className="phase-dot" style={{ backgroundColor: color }} />
      {PHASE_LABELS[phase] || phase}
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
          {aggregates.map(stat => (
            <tr key={stat.phase}>
              <td><PhasePill phase={stat.phase} /></td>
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
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProjectSummary({ workItems, totalWorkItems }) {
  const totalDuration = workItems.reduce((sum, item) => {
    const wall = item.entries.find(e => e.phase === 'total_wall_time')
    return sum + (wall?.duration_ms || 0)
  }, 0)

  const issueCount = new Set(
    workItems.filter(i => i.issue_id).map(i => i.issue_id)
  ).size

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

function IssueGroup({ issueKey, issueId, issueTitle, items }) {
  const [expanded, setExpanded] = useState(false)

  // Collect all entries across work items for this issue (excluding total_wall_time)
  const allEntries = items.flatMap(item =>
    item.entries.filter(e => e.duration_ms != null && e.phase !== 'total_wall_time')
  )

  const totalDuration = allEntries.reduce((sum, e) => sum + (e.duration_ms || 0), 0)
  const maxEntryDuration = allEntries.length > 0
    ? Math.max(...allEntries.map(e => e.duration_ms || 0))
    : 1

  // Extract issue display ID
  const displayId = issueId
    ? (() => {
        const match = issueId.match(/(\d+)$/)
        return match ? `#${match[1]}` : issueId
      })()
    : null

  const latestTime = items.length > 0
    ? items.reduce((latest, item) => {
        const t = new Date(item.created_at).getTime()
        return t > latest ? t : latest
      }, 0)
    : null

  return (
    <div className="issue-group">
      <div className="issue-group-header" onClick={() => setExpanded(!expanded)}>
        <span className="issue-group-expand">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <div className="issue-group-primary">
          {displayId ? (
            <>
              <span className="issue-group-id">{displayId}</span>
              {issueTitle && <span className="issue-group-title">{issueTitle}</span>}
            </>
          ) : (
            <span className="issue-group-no-issue">No associated issue</span>
          )}
        </div>
        <div className="issue-group-stats">
          <span className="issue-group-calls">{allEntries.length} calls</span>
          <span className="issue-group-duration">{formatDuration(totalDuration)}</span>
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

/** Group work items by issue, returning sorted groups */
function groupByIssue(workItems) {
  const groups = new Map()

  for (const item of workItems) {
    const key = item.issue_id || `_no_issue_${item.work_id}`
    if (!groups.has(key)) {
      groups.set(key, {
        issueKey: key,
        issueId: item.issue_id,
        issueTitle: item.issue_title,
        items: []
      })
    }
    const group = groups.get(key)
    // Update title if we get a better one
    if (item.issue_title && !group.issueTitle) {
      group.issueTitle = item.issue_title
    }
    group.items.push(item)
  }

  // Sort: issues with IDs first (by most recent), then no-issue items
  return [...groups.values()].sort((a, b) => {
    if (a.issueId && !b.issueId) return -1
    if (!a.issueId && b.issueId) return 1
    // Sort by most recent work item
    const aTime = Math.max(...a.items.map(i => new Date(i.created_at).getTime()))
    const bTime = Math.max(...b.items.map(i => new Date(i.created_at).getTime()))
    return bTime - aTime
  })
}

function TimingPage() {
  const { workItems, aggregates, totalWorkItems, loading, error, refresh } = useTiming({
    pollInterval: 10000,
    limit: 20
  })

  const issueGroups = useMemo(() => groupByIssue(workItems), [workItems])

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

      {/* Issues Section */}
      <section className="timing-section">
        <header className="section-header">
          <h2 className="section-title">
            <Clock size={16} />
            Issues
          </h2>
        </header>
        {issueGroups.length === 0 ? (
          <p className="timing-empty">No timing data yet. Timing data will appear when compute instances process work items.</p>
        ) : (
          <div className="issue-groups-list">
            {issueGroups.map(group => (
              <IssueGroup
                key={group.issueKey}
                issueKey={group.issueKey}
                issueId={group.issueId}
                issueTitle={group.issueTitle}
                items={group.items}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TimingPage
export { formatDuration, cleanToolName, groupByIssue, LONG_RUNNING_THRESHOLD_MS }
