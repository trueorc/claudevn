import { useState } from 'react'
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

function AggregateStatsTable({ aggregates }) {
  if (!aggregates.length) {
    return <p className="timing-empty">No aggregate data yet</p>
  }

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
              <td>
                <span className="phase-badge" style={{ borderLeftColor: PHASE_COLORS[stat.phase] || '#94a3b8' }}>
                  {PHASE_LABELS[stat.phase] || stat.phase}
                </span>
              </td>
              <td className="timing-num">{stat.count}</td>
              <td className="timing-num">{formatDuration(stat.avg_ms)}</td>
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

function WaterfallBar({ entries, maxDuration }) {
  if (!entries.length || !maxDuration) return null

  // Find the earliest start time among all entries
  const starts = entries.map(e => new Date(e.start).getTime())
  const minStart = Math.min(...starts)

  return (
    <div className="waterfall-chart">
      {entries.map((entry, idx) => {
        const start = new Date(entry.start).getTime()
        const duration = entry.duration_ms || 0
        const offset = ((start - minStart) / maxDuration) * 100
        const width = (duration / maxDuration) * 100

        return (
          <div key={idx} className="waterfall-row">
            <span className="waterfall-label">{PHASE_LABELS[entry.phase] || entry.phase}</span>
            <div className="waterfall-track">
              <div
                className="waterfall-bar"
                style={{
                  left: `${Math.min(offset, 98)}%`,
                  width: `${Math.max(width, 0.5)}%`,
                  backgroundColor: PHASE_COLORS[entry.phase] || '#94a3b8'
                }}
                title={`${PHASE_LABELS[entry.phase] || entry.phase}: ${formatDuration(duration)}`}
              />
            </div>
            <span className="waterfall-duration">{formatDuration(duration)}</span>
          </div>
        )
      })}
    </div>
  )
}

function WorkItemRow({ item }) {
  const [expanded, setExpanded] = useState(false)

  const completedEntries = item.entries.filter(e => e.duration_ms != null)
  const totalDuration = completedEntries.reduce((sum, e) => sum + (e.duration_ms || 0), 0)

  // Max duration for waterfall scaling (use total_wall_time if available, else sum)
  const wallTime = completedEntries.find(e => e.phase === 'total_wall_time')
  const maxDuration = wallTime?.duration_ms || totalDuration || 1

  return (
    <div className="work-item-row">
      <div className="work-item-header" onClick={() => setExpanded(!expanded)}>
        <span className="work-item-expand">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="work-item-id">{item.work_id}</span>
        <span className="work-item-instance">{item.instance_id}</span>
        <span className="work-item-phases">{completedEntries.length} phases</span>
        <span className="work-item-total">{formatDuration(totalDuration)}</span>
        <span className="work-item-time">{formatTimestamp(item.created_at)}</span>
      </div>
      {expanded && (
        <div className="work-item-detail">
          <WaterfallBar entries={completedEntries} maxDuration={maxDuration} />
          <div className="work-item-entries">
            {item.entries.map((entry, idx) => (
              <div key={idx} className="entry-row">
                <span className="entry-phase" style={{ borderLeftColor: PHASE_COLORS[entry.phase] || '#94a3b8' }}>
                  {PHASE_LABELS[entry.phase] || entry.phase}
                </span>
                <span className="entry-start">{formatTimestamp(entry.start)}</span>
                <span className="entry-duration">{formatDuration(entry.duration_ms)}</span>
                {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                  <span className="entry-meta">
                    {Object.entries(entry.metadata).map(([k, v]) => `${k}=${v}`).join(', ')}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TimingPage() {
  const { workItems, aggregates, totalWorkItems, loading, error, refresh } = useTiming({
    pollInterval: 10000,
    limit: 20
  })

  if (loading && !workItems.length) {
    return (
      <div className="page">
        <header className="page-header">
          <h1 className="page-title">Compute Timing</h1>
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
            Compute Timing
          </h1>
          <span className="timing-total-count">{totalWorkItems} work items tracked</span>
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

      {/* Per-Work-Item Timing Section */}
      <section className="timing-section">
        <header className="section-header">
          <h2 className="section-title">
            <Clock size={16} />
            Recent Work Items
          </h2>
        </header>
        {workItems.length === 0 ? (
          <p className="timing-empty">No timing data yet. Timing data will appear when compute instances process work items.</p>
        ) : (
          <div className="work-items-list">
            {workItems.map((item, idx) => (
              <WorkItemRow key={`${item.work_id}-${item.instance_id}-${idx}`} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TimingPage
