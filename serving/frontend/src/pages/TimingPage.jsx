import { useState, useMemo } from 'react'
import { RefreshCw, Clock, BarChart3, Timer, ChevronDown, ChevronRight, Eye, EyeOff } from 'lucide-react'
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

function SourceBadge({ type }) {
  const config = {
    directive: { label: 'DIRECTIVE', className: 'source-badge-directive' },
    issue: { label: 'ISSUE', className: 'source-badge-issue' },
    untracked: { label: 'UNTRACKED', className: 'source-badge-untracked' },
  }
  const { label, className } = config[type] || config.untracked
  return <span className={`source-badge ${className}`}>{label}</span>
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

function ProjectSummary({ projectSummary }) {
  if (!projectSummary) return null

  return (
    <div className="timing-project-summary">
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Total Time</span>
        <span className="timing-project-stat-value accent">{formatDuration(projectSummary.total_duration_ms)}</span>
      </div>
      <div className="timing-project-divider" />
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Directives</span>
        <span className="timing-project-stat-value">{projectSummary.directive_count}</span>
      </div>
      <div className="timing-project-divider" />
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Issues</span>
        <span className="timing-project-stat-value">{projectSummary.issue_count}</span>
      </div>
      <div className="timing-project-divider" />
      <div className="timing-project-stat">
        <span className="timing-project-stat-label">Events</span>
        <span className="timing-project-stat-value">{projectSummary.timing_event_count}</span>
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

function IssueGroup({ issueId, issueTitle, items, badge }) {
  const [expanded, setExpanded] = useState(false)

  const allEntries = items.flatMap(item =>
    item.entries.filter(e => e.duration_ms != null && e.phase !== 'total_wall_time')
  )

  const totalDuration = allEntries.reduce((sum, e) => sum + (e.duration_ms || 0), 0)
  const maxEntryDuration = allEntries.length > 0
    ? Math.max(...allEntries.map(e => e.duration_ms || 0))
    : 1

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
        {badge && <SourceBadge type={badge} />}
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

function DirectiveGroup({ directiveId, directiveText, issueGroups }) {
  const [expanded, setExpanded] = useState(false)

  const totalDuration = issueGroups.reduce((sum, group) => {
    return sum + group.items.reduce((s, item) => {
      const wall = item.entries.find(e => e.phase === 'total_wall_time')
      return s + (wall?.duration_ms || 0)
    }, 0)
  }, 0)

  const issueCount = issueGroups.length

  return (
    <div className="issue-group directive-group">
      <div className="issue-group-header" onClick={() => setExpanded(!expanded)}>
        <span className="issue-group-expand">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <SourceBadge type="directive" />
        <div className="issue-group-primary">
          <span className="issue-group-title">{directiveText || directiveId}</span>
        </div>
        <div className="issue-group-stats">
          <span className="issue-group-calls">{issueCount} {issueCount === 1 ? 'issue' : 'issues'}</span>
          <span className="issue-group-duration">{formatDuration(totalDuration)}</span>
        </div>
      </div>
      {expanded && (
        <div className="issue-group-detail directive-children">
          {issueGroups.map(group => (
            <IssueGroup
              key={group.issueKey}
              issueId={group.issueId}
              issueTitle={group.issueTitle}
              items={group.items}
              badge="issue"
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Group work items into three tiers:
 * 1. Directives - items with directive_id, grouped by directive then by issue
 * 2. Issues - items with issue_id but no directive_id
 * 3. Untracked - items with neither
 */
function groupByTier(workItems) {
  const directiveMap = new Map()  // directive_id -> { directiveText, issueMap }
  const issueOnly = new Map()     // issue_id -> { issueId, issueTitle, items }
  const untracked = []            // items with no issue or directive

  for (const item of workItems) {
    if (item.directive_id) {
      // Tier 1: Directive
      if (!directiveMap.has(item.directive_id)) {
        directiveMap.set(item.directive_id, {
          directiveId: item.directive_id,
          directiveText: item.directive_text,
          issueMap: new Map(),
        })
      }
      const dGroup = directiveMap.get(item.directive_id)
      if (item.directive_text && !dGroup.directiveText) {
        dGroup.directiveText = item.directive_text
      }
      const issueKey = item.issue_id || `_no_issue_${item.work_id}`
      if (!dGroup.issueMap.has(issueKey)) {
        dGroup.issueMap.set(issueKey, {
          issueKey,
          issueId: item.issue_id,
          issueTitle: item.issue_title,
          items: [],
        })
      }
      const iGroup = dGroup.issueMap.get(issueKey)
      if (item.issue_title && !iGroup.issueTitle) iGroup.issueTitle = item.issue_title
      iGroup.items.push(item)
    } else if (item.issue_id) {
      // Tier 2: Issue only
      if (!issueOnly.has(item.issue_id)) {
        issueOnly.set(item.issue_id, {
          issueKey: item.issue_id,
          issueId: item.issue_id,
          issueTitle: item.issue_title,
          items: [],
        })
      }
      const group = issueOnly.get(item.issue_id)
      if (item.issue_title && !group.issueTitle) group.issueTitle = item.issue_title
      group.items.push(item)
    } else {
      // Tier 3: Untracked
      untracked.push(item)
    }
  }

  // Convert directive issueMap to sorted arrays
  const directives = [...directiveMap.values()].map(d => ({
    ...d,
    issueGroups: [...d.issueMap.values()].sort((a, b) => {
      const aTime = Math.max(...a.items.map(i => new Date(i.created_at).getTime()))
      const bTime = Math.max(...b.items.map(i => new Date(i.created_at).getTime()))
      return bTime - aTime
    }),
  }))

  // Sort directives by most recent activity
  directives.sort((a, b) => {
    const aTime = Math.max(...a.issueGroups.flatMap(g => g.items.map(i => new Date(i.created_at).getTime())))
    const bTime = Math.max(...b.issueGroups.flatMap(g => g.items.map(i => new Date(i.created_at).getTime())))
    return bTime - aTime
  })

  const issues = [...issueOnly.values()].sort((a, b) => {
    const aTime = Math.max(...a.items.map(i => new Date(i.created_at).getTime()))
    const bTime = Math.max(...b.items.map(i => new Date(i.created_at).getTime()))
    return bTime - aTime
  })

  // Wrap untracked items as individual groups
  const untrackedGroups = untracked.map(item => ({
    issueKey: `_untracked_${item.work_id}`,
    issueId: null,
    issueTitle: null,
    items: [item],
  }))

  return { directives, issues, untrackedGroups }
}

function TimingPage() {
  const { workItems, aggregates, totalWorkItems, projectSummary, loading, error, refresh } = useTiming({
    pollInterval: 10000,
    limit: 20
  })

  const [showUntracked, setShowUntracked] = useState(false)
  const { directives, issues, untrackedGroups } = useMemo(() => groupByTier(workItems), [workItems])

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

  const hasData = directives.length > 0 || issues.length > 0 || untrackedGroups.length > 0

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
      <ProjectSummary projectSummary={projectSummary} />

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

      {/* Three-Tier Timing Display */}
      {!hasData ? (
        <p className="timing-empty">No timing data yet. Timing data will appear when compute instances process work items.</p>
      ) : (
        <>
          {/* Tier 1: Directives */}
          {directives.length > 0 && (
            <section className="timing-section">
              <header className="section-header">
                <h2 className="section-title">
                  <Clock size={16} />
                  Directives
                  <span className="section-count">{directives.length}</span>
                </h2>
              </header>
              <div className="issue-groups-list">
                {directives.map(d => (
                  <DirectiveGroup
                    key={d.directiveId}
                    directiveId={d.directiveId}
                    directiveText={d.directiveText}
                    issueGroups={d.issueGroups}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Tier 2: Issues (no directive parent) */}
          {issues.length > 0 && (
            <section className="timing-section">
              <header className="section-header">
                <h2 className="section-title">
                  <Clock size={16} />
                  Issues
                  <span className="section-count">{issues.length}</span>
                </h2>
              </header>
              <div className="issue-groups-list">
                {issues.map(group => (
                  <IssueGroup
                    key={group.issueKey}
                    issueId={group.issueId}
                    issueTitle={group.issueTitle}
                    items={group.items}
                    badge="issue"
                  />
                ))}
              </div>
            </section>
          )}

          {/* Tier 3: Untracked */}
          {untrackedGroups.length > 0 && (
            <section className="timing-section">
              <header className="section-header">
                <h2 className="section-title">
                  <Clock size={16} />
                  Untracked
                  <span className="section-count">{untrackedGroups.length}</span>
                </h2>
                <button
                  className="untracked-toggle"
                  onClick={() => setShowUntracked(!showUntracked)}
                >
                  {showUntracked ? <EyeOff size={14} /> : <Eye size={14} />}
                  {showUntracked ? 'Hide' : 'Show'}
                </button>
              </header>
              {showUntracked && (
                <div className="issue-groups-list">
                  {untrackedGroups.map(group => (
                    <IssueGroup
                      key={group.issueKey}
                      issueId={group.issueId}
                      issueTitle={group.issueTitle}
                      items={group.items}
                      badge="untracked"
                    />
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}

export default TimingPage
export { formatDuration, cleanToolName, groupByTier, LONG_RUNNING_THRESHOLD_MS }
