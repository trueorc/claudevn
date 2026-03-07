import { useNavigate } from 'react-router-dom'
import { Activity, Package, Cpu, Clock } from 'lucide-react'
import useIssues from '../../hooks/useIssues'
import usePlanSummary from '../../hooks/usePlanSummary'
import { useProjectContext } from '../../contexts/ProjectContext'
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

function NetworkCard() {
  const navigate = useNavigate()
  return (
    <button className="summary-card" onClick={() => navigate('/network')}>
      <div className="summary-card-header">
        <Cpu size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Network</h3>
      </div>
      <p className="summary-card-link">View health &rarr;</p>
    </button>
  )
}

function TimingCard() {
  const navigate = useNavigate()
  return (
    <button className="summary-card" onClick={() => navigate('/timing')}>
      <div className="summary-card-header">
        <Clock size={14} className="summary-card-icon" />
        <h3 className="summary-card-title">Timing</h3>
      </div>
      <p className="summary-card-link">View metrics &rarr;</p>
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

  return (
    <div className="dashboard-summary-panel">
      <PlanCard planData={planData} />
      <BacklogCard stats={stats} />
      <NetworkCard />
      <TimingCard />
    </div>
  )
}

export default SummaryCards
