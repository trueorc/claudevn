import { useNavigate } from 'react-router-dom'
import { Activity, Cpu, Plus } from 'lucide-react'
import './LeftPanels.css'

// ---------------------------------------------------------------------------
// Panel 1: Project Switcher
// ---------------------------------------------------------------------------
function ProjectSwitcherPanel({ projects = [], activeProject, onSelectProject, onNewProject }) {
  return (
    <div className="lp-panel">
      <div className="lp-panel-header">
        <span className="lp-panel-title">Projects</span>
        <button className="lp-icon-btn" onClick={onNewProject} title="New project" aria-label="New project">
          <Plus size={12} />
        </button>
      </div>

      {projects.length === 0 ? (
        <p className="lp-empty-text">No projects yet</p>
      ) : (
        <div className="lp-project-list">
          {projects.map((project) => {
            const isActive = activeProject?.project_id === project.project_id
            return (
              <button
                key={project.project_id}
                className={`lp-project-row${isActive ? ' lp-project-row--active' : ''}`}
                onClick={() => onSelectProject(project)}
                title={project.name}
              >
                <span
                  className="lp-project-dot"
                  style={{ background: project.color || 'var(--primary)' }}
                />
                <span className="lp-project-name">{project.name}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SVG Progress Ring helper
// ---------------------------------------------------------------------------
function ProgressRing({ pct, size = 64, strokeWidth = 6 }) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (pct / 100) * circumference

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="lp-ring-svg"
      aria-hidden="true"
    >
      {/* Background track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--border-light)"
        strokeWidth={strokeWidth}
      />
      {/* Progress arc */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--status-online)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        className="lp-ring-arc"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Panel 2: Execution Status
// ---------------------------------------------------------------------------
function ExecutionPanel({ planData }) {
  const navigate = useNavigate()

  const active = planData?.in_progress_count ?? planData?.active_count ?? 0
  const queued = planData?.ready_count ?? planData?.queued_count ?? 0
  const blocked = planData?.blocked_count ?? 0
  const done = planData?.done_count ?? 0
  const total = planData?.total_count ?? (active + queued + blocked + done)
  const focusSummary = planData?.focus_summary
  const runningItems = planData?.running_items ?? []

  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const displayedItems = runningItems.slice(0, 3)
  const extraCount = runningItems.length - displayedItems.length

  return (
    <button className="lp-panel lp-panel--clickable" onClick={() => navigate('/plan')}>
      <div className="lp-panel-header">
        <Activity size={12} className="lp-panel-icon" />
        <span className="lp-panel-title">Execution</span>
      </div>

      {/* Progress ring */}
      <div className="lp-ring-wrap">
        <div className="lp-ring-container">
          <ProgressRing pct={pct} />
          <span className="lp-ring-label">
            {total > 0 ? `${pct}%` : '—'}
          </span>
        </div>
      </div>

      {/* Stat pills */}
      <div className="lp-stat-pills">
        <span className="lp-stat-pill">
          <span className="lp-stat-dot lp-stat-dot--online" />
          <span className="lp-stat-count">{active}</span>
          <span className="lp-stat-pill-label">active</span>
        </span>
        <span className="lp-stat-pill">
          <span className="lp-stat-dot lp-stat-dot--pending" />
          <span className="lp-stat-count">{queued}</span>
          <span className="lp-stat-pill-label">queued</span>
        </span>
        <span className="lp-stat-pill">
          <span className="lp-stat-dot lp-stat-dot--offline" />
          <span className="lp-stat-count">{blocked}</span>
          <span className="lp-stat-pill-label">blocked</span>
        </span>
      </div>

      {/* Running items mini-list */}
      {displayedItems.length > 0 && (
        <div className="lp-running-list">
          {displayedItems.map((item, idx) => (
            <div key={item.id ?? idx} className="lp-running-item">
              <span className="lp-pulse-dot" />
              <span className="lp-running-title">{item.title}</span>
            </div>
          ))}
          {extraCount > 0 && (
            <span className="lp-running-more">+{extraCount} more</span>
          )}
        </div>
      )}

      {/* Focus summary */}
      {focusSummary && (
        <p className="lp-focus-summary" title={focusSummary}>{focusSummary}</p>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Panel 3: Network Health
// ---------------------------------------------------------------------------
function NetworkPanel({ health, overallStatus, healthLoading }) {
  const navigate = useNavigate()

  const computeByStatus = health?.compute_registry?.by_status ?? {}
  const computeTotal = health?.compute_registry?.total_instances ?? 0
  const computeOnline = computeByStatus.online ?? 0

  const marketplaceByStatus = health?.marketplace_registry?.by_status ?? {}
  const marketplaceTotal = health?.marketplace_registry?.total_instances ?? 0
  const marketplaceOnline = marketplaceByStatus.online ?? 0

  // Build an array of node status entries for the dot grid
  const nodeDots = []
  const statusOrder = ['online', 'degraded', 'offline']
  for (const status of statusOrder) {
    const count = computeByStatus[status] ?? 0
    for (let i = 0; i < count; i++) {
      nodeDots.push(status)
    }
  }
  // Unknown nodes = total minus known statuses
  const knownCount = nodeDots.length
  const unknownCount = Math.max(0, computeTotal - knownCount)
  for (let i = 0; i < unknownCount; i++) {
    nodeDots.push('unknown')
  }

  const statusDotClass = {
    online: 'lp-node-dot--online',
    degraded: 'lp-node-dot--degraded',
    offline: 'lp-node-dot--offline',
    unknown: 'lp-node-dot--unknown',
  }

  return (
    <button className="lp-panel lp-panel--clickable" onClick={() => navigate('/network')}>
      <div className="lp-panel-header">
        <Cpu size={12} className="lp-panel-icon" />
        <span className="lp-panel-title">Network</span>
        {!healthLoading && (
          <span className={`lp-health-dot lp-health-dot--${overallStatus ?? 'unknown'}`} />
        )}
      </div>

      {nodeDots.length > 0 ? (
        <div className="lp-node-grid" aria-label="Compute node status grid">
          {nodeDots.map((status, idx) => (
            <span
              key={idx}
              className={`lp-node-dot ${statusDotClass[status] ?? statusDotClass.unknown}`}
              title={status}
            />
          ))}
        </div>
      ) : (
        <p className="lp-empty-text">
          {healthLoading ? 'Loading…' : 'No compute nodes'}
        </p>
      )}

      <p className="lp-network-summary">
        {computeOnline} online / {computeTotal} total
      </p>

      {marketplaceTotal > 0 && (
        <p className="lp-network-marketplace">
          Marketplace: {marketplaceOnline}/{marketplaceTotal}
        </p>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Root export
// ---------------------------------------------------------------------------
function LeftPanels({
  projects,
  activeProject,
  onSelectProject,
  onNewProject,
  planData,
  health,
  overallStatus,
  healthLoading,
}) {
  return (
    <div className="lp-column">
      <ProjectSwitcherPanel
        projects={projects}
        activeProject={activeProject}
        onSelectProject={onSelectProject}
        onNewProject={onNewProject}
      />
      <ExecutionPanel planData={planData} />
      <NetworkPanel
        health={health}
        overallStatus={overallStatus}
        healthLoading={healthLoading}
      />
    </div>
  )
}

export default LeftPanels
