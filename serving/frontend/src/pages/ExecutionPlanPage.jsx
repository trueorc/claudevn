import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Pause, Play } from 'lucide-react'
import SummaryBar from '../components/plan/SummaryBar'
import ActiveWorkView from '../components/plan/ActiveWorkView'
import PipelineHealth from '../components/plan/PipelineHealth'
import StuckWorkDetector from '../components/plan/StuckWorkDetector'
import EventActivityLog from '../components/plan/EventActivityLog'
import IssueDetailModal from '../components/workmap/IssueDetailModal'
import EmptyState from '../components/common/EmptyState'
import { PageSubtitle } from '../components/common/InlineHint'
import usePlanSummary from '../hooks/usePlanSummary'
import useEventStream from '../hooks/useEventStream'
import { useProjectContext } from '../contexts/ProjectContext'
import { getOrchestratorStatus, pauseOrchestrator, resumeOrchestrator } from '../api/orchestrator'
import './ExecutionPlanPage.css'

function ExecutionPlanPage() {
  const { activeProject } = useProjectContext()
  const activeProjectId = activeProject?.project_id || null
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)

  // Live event stream for activity log and stuck detection
  const [activityEvents, setActivityEvents] = useState([])
  const [stuckItems, setStuckItems] = useState([])
  const [pipelineLayers, setPipelineLayers] = useState({})

  useEventStream({
    patterns: ['execution.*', 'verification.*', 'decomposition.*'],
    projectId: activeProjectId,
    enabled: !!activeProjectId,
    onEvent: useCallback((event) => {
      // Append to activity log (newest first)
      setActivityEvents(prev => [event, ...prev].slice(0, 500))

      // Update pipeline health from events
      const layer = event.event?.split('.')[0]
      if (layer) {
        setPipelineLayers(prev => ({
          ...prev,
          [layer === 'execution' ? 'dispatch' : layer]: {
            status: event.event.includes('failed') ? 'degraded' : 'healthy',
            detail: event.event.includes('failed')
              ? `Last failure: ${event.work_unit_id || ''}`
              : `Last activity: ${event.event}`,
            active_count: prev[layer === 'execution' ? 'dispatch' : layer]?.active_count,
          },
        }))
      }

      // Detect failures for stuck work
      if (event.event === 'execution.failed') {
        setStuckItems(prev => [...prev, {
          type: 'failed',
          work_unit_id: event.work_unit_id,
          description: `Execution failed: ${event.reason || 'unknown'}`,
          reason: event.reason,
          id: event.work_unit_id,
        }])
      }
      if (event.event === 'verification.failed') {
        setStuckItems(prev => [...prev, {
          type: 'failed',
          work_unit_id: event.work_unit_id,
          description: `Verification failed`,
          reason: event.details || event.failed_checks?.join(', '),
          id: event.work_unit_id,
        }])
      }
    }, []),
  })

  // Fetch pause state
  useEffect(() => {
    let cancelled = false
    getOrchestratorStatus()
      .then(status => { if (!cancelled) setPaused(!!status?.paused) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const togglePause = useCallback(async () => {
    setPauseLoading(true)
    try {
      if (paused) {
        await resumeOrchestrator()
        setPaused(false)
      } else {
        await pauseOrchestrator()
        setPaused(true)
      }
    } catch (err) {
      console.warn('Failed to toggle pause:', err)
    } finally {
      setPauseLoading(false)
    }
  }, [paused])

  const { data, loading, error, refresh } = usePlanSummary(activeProjectId)

  if (!activeProjectId) {
    return (
      <div className="page">
        <header className="page-header">
          <div className="header-content">
            <h1 className="page-title">Execution</h1>
            <PageSubtitle>Queue and pipeline observability</PageSubtitle>
          </div>
        </header>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar to view execution status." />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div className="header-content">
          <h1 className="page-title">Execution</h1>
          <PageSubtitle>Queues, pipeline health, and activity for {activeProject?.name}</PageSubtitle>
          <div className="plan-header-controls">
            <button
              className={`plan-pause-btn ${paused ? 'plan-pause-btn--paused' : ''}`}
              onClick={togglePause}
              disabled={pauseLoading}
              title={paused ? 'Resume dispatch' : 'Pause dispatch'}
            >
              {paused ? <Play size={14} /> : <Pause size={14} />}
              <span>{paused ? 'Resume' : 'Pause'}</span>
            </button>
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {paused && (
        <div className="plan-paused-banner">
          <Pause size={14} />
          <span>Dispatch is paused. In-flight work will complete, but no new work will be assigned.</span>
          <button className="plan-paused-resume" onClick={togglePause} disabled={pauseLoading}>Resume</button>
        </div>
      )}

      {/* Stuck / failed work — top of page, can't miss it */}
      <StuckWorkDetector items={stuckItems} />

      {/* Pipeline health — per-layer status */}
      <PipelineHealth layers={pipelineLayers} />

      {/* Summary counts */}
      <SummaryBar data={data} loading={loading} />

      {/* Queue columns — Running / Up Next / Blocked / Failed */}
      <ActiveWorkView
        data={data}
        loading={loading}
        onItemClick={(item) => setSelectedIssue(item)}
        onItemTracesClick={() => {}}
        itemBucketMap={{}}
      />

      {/* Real-time event activity log — nothing fails silently */}
      <EventActivityLog events={activityEvents} />

      <IssueDetailModal
        isOpen={Boolean(selectedIssue)}
        onClose={() => setSelectedIssue(null)}
        issue={selectedIssue}
        onSuccess={refresh}
        viewOnly
      />
    </div>
  )
}

export default ExecutionPlanPage
