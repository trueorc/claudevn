import { useNavigate } from 'react-router-dom'
import { Activity, Package, Cpu, Clock, Users } from 'lucide-react'
import useIssues from '../../hooks/useIssues'
import usePlanSummary from '../../hooks/usePlanSummary'
import usePresence from '../../hooks/usePresence'
import useSystemHealth from '../../hooks/useSystemHealth'
import { useProjectContext } from '../../contexts/ProjectContext'
import UserAvatar from '../common/UserAvatar'
import './SummaryCards.css'

function PlanCard({ planData }) {
  const navigate = useNavigate()
  const active = planData?.active_count || 0
  const queued = planData?.queued_count || 0
  const total = active + queued

  return (
    <button className="summary-card" onClick={() => navigate('/plan')}>
      <div className="summary-card-header">
        <Activity size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Execution</h3>
      </div>
      {total > 0 ? (
        <div className="summary-card-body">
          <div className="summary-card-stat">
            <span className="summary-stat-value">{active}</span>
            <span className="summary-stat-label">active</span>
          </div>
          <div className="summary-card-stat">
            <span className="summary-stat-value">{queued}</span>
            <span className="summary-stat-label">queued</span>
          </div>
        </div>
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

  return (
    <button className="summary-card" onClick={() => navigate('/backlog')}>
      <div className="summary-card-header">
        <Package size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Backlog</h3>
        {total > 0 && <span className="summary-card-count">{total}</span>}
      </div>
      {total > 0 ? (
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
      ) : (
        <p className="summary-card-empty">Empty backlog</p>
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

function NetworkCard() {
  const navigate = useNavigate()
  const { health, overallStatus, loading } = useSystemHealth({ pollInterval: 30000 })

  const byStatus = health?.compute_registry?.by_status || {}
  const totalCount = health?.compute_registry?.total_instances || 0
  const onlineCount = byStatus.online || 0

  return (
    <button className="summary-card" onClick={() => navigate('/network')}>
      <div className="summary-card-header">
        <Cpu size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Network</h3>
        {!loading && (
          <span className={`summary-card-health-dot summary-health-${overallStatus || 'unknown'}`} />
        )}
      </div>
      {totalCount > 0 ? (
        <div className="summary-card-body">
          <div className="summary-card-stat">
            <span className="summary-stat-value summary-stat-done">{onlineCount}</span>
            <span className="summary-stat-label">online</span>
          </div>
          <div className="summary-card-stat">
            <span className="summary-stat-value">{totalCount}</span>
            <span className="summary-stat-label">total</span>
          </div>
        </div>
      ) : (
        <p className="summary-card-empty">{loading ? 'Loading...' : 'No compute nodes'}</p>
      )}
    </button>
  )
}

function TimingCard() {
  const navigate = useNavigate()
  const { health } = useSystemHealth({ pollInterval: 30000 })

  const uptime = health?.uptime
  const activeSessions = health?.active_sessions || 0

  const formatUptime = (seconds) => {
    if (!seconds) return null
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
    return `${Math.floor(seconds / 86400)}d`
  }

  const uptimeFormatted = formatUptime(uptime)

  return (
    <button className="summary-card" onClick={() => navigate('/timing')}>
      <div className="summary-card-header">
        <Clock size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Timing</h3>
      </div>
      {(uptimeFormatted || activeSessions > 0) ? (
        <div className="summary-card-body">
          {uptimeFormatted && (
            <div className="summary-card-stat">
              <span className="summary-stat-value">{uptimeFormatted}</span>
              <span className="summary-stat-label">uptime</span>
            </div>
          )}
          {activeSessions > 0 && (
            <div className="summary-card-stat">
              <span className="summary-stat-value">{activeSessions}</span>
              <span className="summary-stat-label">sessions</span>
            </div>
          )}
        </div>
      ) : (
        <p className="summary-card-empty">No timing data</p>
      )}
    </button>
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
      <TimingCard />
    </div>
  )
}

export default SummaryCards
