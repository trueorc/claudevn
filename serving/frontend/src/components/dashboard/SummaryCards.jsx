import { useNavigate } from 'react-router-dom'
import { Activity, Package, Cpu, Clock, Users } from 'lucide-react'
import useIssues from '../../hooks/useIssues'
import usePlanSummary from '../../hooks/usePlanSummary'
import usePresence from '../../hooks/usePresence'
import useSystemHealth from '../../hooks/useSystemHealth'
import useTiming from '../../hooks/useTiming'
import { useProjectContext } from '../../contexts/ProjectContext'
import UserAvatar from '../common/UserAvatar'
import './SummaryCards.css'

function formatDuration(ms) {
  if (ms == null || ms === 0) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`
  return `${(ms / 3600000).toFixed(1)}h`
}

function PlanCard({ planData }) {
  const navigate = useNavigate()
  const active = planData?.in_progress_count || planData?.active_count || 0
  const queued = planData?.ready_count || planData?.queued_count || 0
  const blocked = planData?.blocked_count || 0
  const failed = planData?.failed_count || 0
  const done = planData?.done_count || 0
  const total = planData?.total_count || (active + queued + blocked + failed + done)
  const focusSummary = planData?.focus_summary
  const presetLabel = planData?.active_preset_label
  const presetColor = planData?.active_preset_color

  const progressPct = total > 0 ? Math.round((done / total) * 100) : 0
  const hasActivity = active > 0 || queued > 0 || blocked > 0 || failed > 0

  return (
    <button className="summary-card" onClick={() => navigate('/plan')}>
      <div className="summary-card-header">
        <Activity size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Execution</h3>
        {presetLabel && (
          <span className="summary-preset-badge">
            {presetColor && (
              <span className="summary-preset-dot" style={{ background: presetColor }} />
            )}
            {presetLabel}
          </span>
        )}
      </div>
      {hasActivity ? (
        <>
          <div className="summary-card-body">
            {active > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-done">{active}</span>
                <span className="summary-stat-label">active</span>
              </div>
            )}
            {queued > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value">{queued}</span>
                <span className="summary-stat-label">queued</span>
              </div>
            )}
            {blocked > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-blocked">{blocked}</span>
                <span className="summary-stat-label">blocked</span>
              </div>
            )}
            {failed > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-failed">{failed}</span>
                <span className="summary-stat-label">failed</span>
              </div>
            )}
            {total > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value">{done}</span>
                <span className="summary-stat-label">/ {total} done</span>
              </div>
            )}
          </div>
          {total > 0 && (
            <div className="summary-progress-bar">
              <div
                className="summary-progress-fill"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          )}
          {focusSummary && (
            <p className="summary-card-focus" title={focusSummary}>{focusSummary}</p>
          )}
        </>
      ) : (
        <p className="summary-card-empty">No active work</p>
      )}
    </button>
  )
}

function BacklogCard({ stats }) {
  const navigate = useNavigate()
  const ready = (stats?.by_status?.ready || 0) + (stats?.by_status?.pending || 0)
  const blocked = stats?.by_status?.blocked || 0
  const inReview = (stats?.by_status?.in_review || 0) + (stats?.by_status?.testing || 0)
  const done = stats?.by_status?.done || 0
  const total = stats?.total || 0
  const p0 = stats?.by_priority?.P0 || 0
  const p1 = stats?.by_priority?.P1 || 0
  const p2 = stats?.by_priority?.P2 || 0

  const progressPct = total > 0 ? Math.round((done / total) * 100) : 0

  return (
    <button className="summary-card" onClick={() => navigate('/backlog')}>
      <div className="summary-card-header">
        <Package size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Backlog</h3>
        {total > 0 && <span className="summary-card-count">{total}</span>}
      </div>
      {total > 0 ? (
        <>
          <div className="summary-card-body">
            {ready > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-ready">{ready}</span>
                <span className="summary-stat-label">ready</span>
              </div>
            )}
            {blocked > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-blocked">{blocked}</span>
                <span className="summary-stat-label">blocked</span>
              </div>
            )}
            {inReview > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-review">{inReview}</span>
                <span className="summary-stat-label">review</span>
              </div>
            )}
            {done > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-done">{done}</span>
                <span className="summary-stat-label">done</span>
              </div>
            )}
          </div>
          <div className="summary-progress-bar">
            <div
              className="summary-progress-fill"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {(p0 > 0 || p1 > 0 || p2 > 0) && (
            <div className="summary-priority-row">
              {p0 > 0 && <span className="summary-priority-pill summary-priority-p0">P0 {p0}</span>}
              {p1 > 0 && <span className="summary-priority-pill summary-priority-p1">P1 {p1}</span>}
              {p2 > 0 && <span className="summary-priority-pill">P2 {p2}</span>}
            </div>
          )}
        </>
      ) : (
        <p className="summary-card-empty">Empty backlog</p>
      )}
    </button>
  )
}

function TimingCard({ aggregates, totalWorkItems }) {
  const navigate = useNavigate()

  const wallTimeAggregate = aggregates?.find((a) => a.phase === 'total_wall_time')
  const avgMs = wallTimeAggregate?.avg_ms || null
  const p95Ms = wallTimeAggregate?.p95_ms || null
  const itemCount = wallTimeAggregate?.count || totalWorkItems || 0

  const hasData = avgMs != null || itemCount > 0

  return (
    <button className="summary-card" onClick={() => navigate('/timing')}>
      <div className="summary-card-header">
        <Clock size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Timing</h3>
      </div>
      {hasData ? (
        <div className="summary-card-body">
          {avgMs != null && (
            <div className="summary-card-stat">
              <span className="summary-stat-value">{formatDuration(avgMs)}</span>
              <span className="summary-stat-label">avg</span>
            </div>
          )}
          {p95Ms != null && (
            <div className="summary-card-stat">
              <span className="summary-stat-value">{formatDuration(p95Ms)}</span>
              <span className="summary-stat-label">p95</span>
            </div>
          )}
          {itemCount > 0 && (
            <div className="summary-card-stat">
              <span className="summary-stat-value">{itemCount}</span>
              <span className="summary-stat-label">items</span>
            </div>
          )}
        </div>
      ) : (
        <p className="summary-card-empty">No timing data</p>
      )}
    </button>
  )
}

function NetworkCard() {
  const navigate = useNavigate()
  const { health, overallStatus, loading } = useSystemHealth({ pollInterval: 30000 })

  const computeByStatus = health?.compute_registry?.by_status || {}
  const computeTotal = health?.compute_registry?.total_instances || 0
  const computeOnline = computeByStatus.online || 0
  const computeDegraded = computeByStatus.degraded || 0

  const marketplaceByStatus = health?.marketplace_registry?.by_status || {}
  const marketplaceTotal = health?.marketplace_registry?.total_instances || 0
  const marketplaceOnline = marketplaceByStatus.online || 0

  const statusText =
    overallStatus === 'healthy'
      ? 'All healthy'
      : overallStatus === 'degraded'
        ? 'Degraded'
        : overallStatus === 'unhealthy' || overallStatus === 'offline'
          ? 'Unhealthy'
          : null

  return (
    <button className="summary-card" onClick={() => navigate('/network')}>
      <div className="summary-card-header">
        <Cpu size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Network</h3>
        {!loading && (
          <span className={`summary-card-health-dot summary-health-${overallStatus || 'unknown'}`} />
        )}
      </div>
      {computeTotal > 0 || marketplaceTotal > 0 ? (
        <>
          <div className="summary-card-body">
            <div className="summary-card-stat">
              <span className="summary-stat-value summary-stat-done">{computeOnline}</span>
              <span className="summary-stat-label">compute</span>
            </div>
            {computeDegraded > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-review">{computeDegraded}</span>
                <span className="summary-stat-label">degraded</span>
              </div>
            )}
            <div className="summary-card-stat">
              <span className="summary-stat-value">{computeTotal}</span>
              <span className="summary-stat-label">total</span>
            </div>
            {marketplaceTotal > 0 && (
              <div className="summary-card-stat">
                <span className="summary-stat-value summary-stat-done">{marketplaceOnline}</span>
                <span className="summary-stat-label">market</span>
              </div>
            )}
          </div>
          {statusText && (
            <p className="summary-status-text">{statusText}</p>
          )}
        </>
      ) : (
        <p className="summary-card-empty">{loading ? 'Loading...' : 'No compute nodes'}</p>
      )}
    </button>
  )
}

function TeamCard({ users }) {
  if (!users || users.length === 0) {
    return (
      <div className="summary-card summary-card-static">
        <div className="summary-card-header">
          <Users size={14} className="summary-card-icon" />
          <h3 className="summary-card-title">Team</h3>
        </div>
        <p className="summary-card-empty">Only you here</p>
      </div>
    )
  }

  return (
    <div className="summary-card summary-card-static">
      <div className="summary-card-header">
        <Users size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Team</h3>
        <span className="summary-card-count">{users.length}</span>
      </div>
      <div className="team-card-users">
        {users.map((user) => (
          <div key={user.user_id} className="team-card-user">
            <UserAvatar
              userId={user.user_id}
              displayName={user.display_name}
              size="sm"
              showStatus
              status={user.status === 'online' ? 'online' : 'away'}
            />
            <div className="team-card-user-info">
              <span className="team-card-user-name">{user.display_name}</span>
              {user.current_view && (
                <span className="team-card-user-view">{user.current_view}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SummaryCards() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null

  const { stats } = useIssues({
    pollInterval: 15000,
    filters: { project_id: projectId },
  })
  const { data: planData } = usePlanSummary(projectId, {
    pollInterval: 15000,
  })
  const { users } = usePresence(projectId)
  const { aggregates, totalWorkItems } = useTiming(projectId, { pollInterval: 30000 })

  if (!activeProject) {
    return (
      <div className="dashboard-summary-panel">
        <TeamCard users={users} />
        <NetworkCard />
      </div>
    )
  }

  return (
    <div className="dashboard-summary-panel">
      <PlanCard planData={planData} />
      <BacklogCard stats={stats} />
      <TeamCard users={users} />
      <NetworkCard />
      <TimingCard aggregates={aggregates} totalWorkItems={totalWorkItems} />
    </div>
  )
}

export default SummaryCards
