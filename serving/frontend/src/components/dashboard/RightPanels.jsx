import { useNavigate } from 'react-router-dom'
import { Package, Clock, Users } from 'lucide-react'
import UserAvatar from '../common/UserAvatar'
import './RightPanels.css'

function formatDuration(ms) {
  if (ms == null || ms === 0) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`
  return `${(ms / 3600000).toFixed(1)}h`
}

const PHASE_SHORT_NAMES = {
  workspace_setup: 'Setup',
  repo_clone: 'Clone',
  sdk_launch: 'SDK',
  mcp_tool_call: 'MCP',
  tool_use: 'Tools',
  api_inference: 'Inference',
  sdk_execution: 'Exec',
  git_push: 'Push',
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
}

// SVG donut chart constants
const DONUT_SIZE = 80
const DONUT_CENTER = 40
const DONUT_RADIUS = 32
const DONUT_STROKE_WIDTH = 12
const DONUT_CIRCUMFERENCE = 2 * Math.PI * DONUT_RADIUS

const DONUT_STATUS_CONFIG = [
  { key: 'ready_pending', label: 'Ready', color: 'var(--status-pending)' },
  { key: 'in_progress', label: 'Active', color: 'var(--primary)' },
  { key: 'blocked', label: 'Blocked', color: 'var(--status-offline)' },
  { key: 'in_review', label: 'Review', color: 'var(--status-degraded)' },
  { key: 'done', label: 'Done', color: 'var(--status-online)' },
]

function buildDonutSegments(statusCounts, total) {
  if (total === 0) return []

  const segments = []
  let offsetDeg = 0

  for (const cfg of DONUT_STATUS_CONFIG) {
    const count = statusCounts[cfg.key] || 0
    if (count === 0) continue

    const fraction = count / total
    const arcLen = fraction * DONUT_CIRCUMFERENCE
    // stroke-dashoffset rotates by converting accumulated angle to svg units
    // SVG circles start at the rightmost point (3 o'clock); rotate -90 deg via a CSS transform
    const dashOffset = DONUT_CIRCUMFERENCE - offsetDeg

    segments.push({
      ...cfg,
      count,
      arcLen,
      dashOffset,
    })

    offsetDeg += arcLen
  }

  return segments
}

function DonutChart({ statusCounts, total }) {
  if (total === 0) {
    return (
      <svg
        width={DONUT_SIZE}
        height={DONUT_SIZE}
        viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}
        className="rp-donut-svg"
        aria-label="Backlog donut chart — empty"
      >
        <circle
          cx={DONUT_CENTER}
          cy={DONUT_CENTER}
          r={DONUT_RADIUS}
          fill="none"
          stroke="var(--border-light)"
          strokeWidth={DONUT_STROKE_WIDTH}
        />
        <text
          x={DONUT_CENTER}
          y={DONUT_CENTER}
          textAnchor="middle"
          dominantBaseline="central"
          className="rp-donut-center-text"
        >
          0
        </text>
      </svg>
    )
  }

  const segments = buildDonutSegments(statusCounts, total)

  return (
    <svg
      width={DONUT_SIZE}
      height={DONUT_SIZE}
      viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}
      className="rp-donut-svg"
      aria-label={`Backlog donut chart — ${total} total items`}
    >
      {/* Track ring */}
      <circle
        cx={DONUT_CENTER}
        cy={DONUT_CENTER}
        r={DONUT_RADIUS}
        fill="none"
        stroke="var(--border)"
        strokeWidth={DONUT_STROKE_WIDTH}
      />
      {segments.map((seg) => (
        <circle
          key={seg.key}
          cx={DONUT_CENTER}
          cy={DONUT_CENTER}
          r={DONUT_RADIUS}
          fill="none"
          stroke={seg.color}
          strokeWidth={DONUT_STROKE_WIDTH}
          strokeDasharray={`${seg.arcLen} ${DONUT_CIRCUMFERENCE}`}
          strokeDashoffset={seg.dashOffset}
          strokeLinecap="butt"
          style={{ transform: 'rotate(-90deg)', transformOrigin: `${DONUT_CENTER}px ${DONUT_CENTER}px` }}
        />
      ))}
      <text
        x={DONUT_CENTER}
        y={DONUT_CENTER}
        textAnchor="middle"
        dominantBaseline="central"
        className="rp-donut-center-text"
      >
        {total}
      </text>
    </svg>
  )
}

const STATUS_TAG_CONFIG = {
  in_progress: { label: 'Active', className: 'rp-issue-tag--active' },
  blocked: { label: 'Blocked', className: 'rp-issue-tag--blocked' },
  failed: { label: 'Failed', className: 'rp-issue-tag--blocked' },
  in_review: { label: 'Review', className: 'rp-issue-tag--review' },
  testing: { label: 'Testing', className: 'rp-issue-tag--review' },
  ready: { label: 'Ready', className: 'rp-issue-tag--ready' },
  pending: { label: 'Ready', className: 'rp-issue-tag--ready' },
  backlog: { label: 'Backlog', className: 'rp-issue-tag--backlog' },
  done: { label: 'Done', className: 'rp-issue-tag--done' },
}

const STATUS_SORT_ORDER = {
  in_progress: 0,
  blocked: 1,
  failed: 2,
  in_review: 3,
  testing: 4,
  ready: 5,
  pending: 6,
  backlog: 7,
  done: 8,
}

function BacklogPanel({ stats, issues }) {
  const navigate = useNavigate()

  const ready = (stats?.by_status?.ready || 0) + (stats?.by_status?.pending || 0)
  const inProgress = stats?.by_status?.in_progress || 0
  const blocked = stats?.by_status?.blocked || 0
  const inReview = (stats?.by_status?.in_review || 0) + (stats?.by_status?.testing || 0)
  const done = stats?.by_status?.done || 0
  const total = stats?.total || 0

  const p0 = stats?.by_priority?.P0 || 0
  const p1 = stats?.by_priority?.P1 || 0
  const p2 = stats?.by_priority?.P2 || 0

  const statusCounts = {
    ready_pending: ready,
    in_progress: inProgress,
    blocked,
    in_review: inReview,
    done,
  }

  const visibleLegend = DONUT_STATUS_CONFIG.filter((cfg) => (statusCounts[cfg.key] || 0) > 0)

  // Sort issues by status priority (active/blocked first, done last)
  const sortedIssues = [...(issues || [])].sort(
    (a, b) => (STATUS_SORT_ORDER[a.status] ?? 99) - (STATUS_SORT_ORDER[b.status] ?? 99)
  )

  return (
    <button
      className="rp-panel rp-panel-clickable rp-panel--grow"
      onClick={() => navigate('/backlog')}
      aria-label="Navigate to backlog"
    >
      <div className="rp-panel-header">
        <Package size={14} className="rp-panel-icon" />
        <h3 className="rp-panel-title">BACKLOG</h3>
        {total > 0 && <span className="rp-panel-count">{total}</span>}
      </div>

      <div className="rp-donut-wrapper">
        <DonutChart statusCounts={statusCounts} total={total} />
      </div>

      {visibleLegend.length > 0 && (
        <div className="rp-donut-legend">
          {visibleLegend.map((cfg) => (
            <div key={cfg.key} className="rp-legend-item">
              <span className="rp-legend-swatch" style={{ background: cfg.color }} />
              <span className="rp-legend-label">{cfg.label}</span>
              <span className="rp-legend-count">{statusCounts[cfg.key]}</span>
            </div>
          ))}
        </div>
      )}

      {sortedIssues.length > 0 && (
        <div className="rp-issue-list">
          {sortedIssues.map((issue) => {
            const tag = STATUS_TAG_CONFIG[issue.status]
            return (
              <div key={issue.issue_id} className="rp-issue-row">
                <div className="rp-issue-meta">
                  {tag && (
                    <span className={`rp-issue-tag ${tag.className}`}>{tag.label}</span>
                  )}
                  <span className="rp-issue-id">#{issue.issue_id}</span>
                  {issue.priority && (
                    <span className={`rp-issue-priority rp-issue-priority--${issue.priority.toLowerCase()}`}>
                      {issue.priority}
                    </span>
                  )}
                </div>
                <span className="rp-issue-title">{issue.title}</span>
              </div>
            )
          })}
        </div>
      )}

      {(p0 > 0 || p1 > 0 || p2 > 0) && (
        <div className="rp-priority-row">
          {p0 > 0 && <span className="rp-priority-pill rp-priority-p0">P0 {p0}</span>}
          {p1 > 0 && <span className="rp-priority-pill rp-priority-p1">P1 {p1}</span>}
          {p2 > 0 && <span className="rp-priority-pill">P2 {p2}</span>}
        </div>
      )}
    </button>
  )
}

function TimingPanel({ aggregates, totalWorkItems }) {
  const navigate = useNavigate()

  const wallTimeAggregate = aggregates?.find((a) => a.phase === 'total_wall_time')
  const avgMs = wallTimeAggregate?.avg_ms ?? null
  const p95Ms = wallTimeAggregate?.p95_ms ?? null
  const itemCount = wallTimeAggregate?.count || totalWorkItems || 0

  const hasData = avgMs != null || itemCount > 0

  // Build phase rows: exclude total_wall_time, take top 4 by avg_ms
  const phaseRows = (aggregates || [])
    .filter((a) => a.phase !== 'total_wall_time' && a.avg_ms != null)
    .sort((a, b) => b.avg_ms - a.avg_ms)
    .slice(0, 4)

  const maxPhaseMs = phaseRows.length > 0 ? phaseRows[0].avg_ms : 1

  return (
    <button
      className="rp-panel rp-panel-clickable"
      onClick={() => navigate('/timing')}
      aria-label="Navigate to timing"
    >
      <div className="rp-panel-header">
        <Clock size={14} className="rp-panel-icon" />
        <h3 className="rp-panel-title">TIMING</h3>
      </div>

      {hasData ? (
        <>
          <div className="rp-timing-metrics-row">
            {avgMs != null && (
              <div className="rp-timing-metric">
                <span className="rp-timing-metric-value">{formatDuration(avgMs)}</span>
                <span className="rp-timing-metric-label">avg</span>
              </div>
            )}
            {p95Ms != null && (
              <div className="rp-timing-metric">
                <span className="rp-timing-metric-value">{formatDuration(p95Ms)}</span>
                <span className="rp-timing-metric-label">p95</span>
              </div>
            )}
            {itemCount > 0 && (
              <div className="rp-timing-metric">
                <span className="rp-timing-metric-value">{itemCount}</span>
                <span className="rp-timing-metric-label">items</span>
              </div>
            )}
          </div>

          {phaseRows.length > 0 && (
            <div className="rp-timing-bars">
              {phaseRows.map((phase) => {
                const pct = maxPhaseMs > 0 ? (phase.avg_ms / maxPhaseMs) * 100 : 0
                const color = PHASE_COLORS[phase.phase] || 'var(--text-muted)'
                const label = PHASE_SHORT_NAMES[phase.phase] || phase.phase
                return (
                  <div key={phase.phase} className="rp-timing-bar-row">
                    <span className="rp-timing-bar-label">{label}</span>
                    <div className="rp-timing-bar-track">
                      <div
                        className="rp-timing-bar-fill"
                        style={{ width: `${pct}%`, background: color }}
                      />
                    </div>
                    <span className="rp-timing-bar-value">{formatDuration(phase.avg_ms)}</span>
                  </div>
                )
              })}
            </div>
          )}
        </>
      ) : (
        <p className="rp-panel-empty">No timing data yet</p>
      )}
    </button>
  )
}

function teamStatusToAvatar(status) {
  if (status === 'online') return 'online'
  if (status === 'idle') return 'away'
  return 'offline'
}

function teamActivityLabel(user) {
  const parts = []
  if (user.project_name) parts.push(user.project_name)
  if (user.current_view) parts.push(user.current_view)
  return parts.length > 0 ? parts.join(' · ') : null
}

function TeamPanel({ presenceUsers }) {
  const users = presenceUsers || []
  const onlineCount = users.filter((u) => u.status === 'online').length

  return (
    <div className="rp-panel">
      <div className="rp-panel-header">
        <Users size={14} className="rp-panel-icon" />
        <h3 className="rp-panel-title">TEAM</h3>
        {users.length > 0 && (
          <span className="rp-panel-count">
            {onlineCount > 0 ? onlineCount : users.length}
          </span>
        )}
      </div>

      {users.length === 0 ? (
        <p className="rp-panel-empty">Only you here</p>
      ) : (
        <div className="rp-team-users">
          {users.map((user) => {
            const label = teamActivityLabel(user)
            return (
              <div key={user.user_id} className="rp-team-user">
                <UserAvatar
                  userId={user.user_id}
                  displayName={user.display_name}
                  size="sm"
                  showStatus
                  status={teamStatusToAvatar(user.status)}
                />
                <div className="rp-team-user-info">
                  <span className="rp-team-user-name">{user.display_name}</span>
                  {label && (
                    <span className="rp-team-user-view">{label}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function RightPanels({ stats, issues, aggregates, totalWorkItems, presenceUsers }) {
  return (
    <div className="rp-column">
      <BacklogPanel stats={stats} issues={issues} />
      <TimingPanel aggregates={aggregates} totalWorkItems={totalWorkItems} />
      <TeamPanel presenceUsers={presenceUsers} />
    </div>
  )
}

export default RightPanels
