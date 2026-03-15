import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, List, Layers, Network, Pause, Play } from 'lucide-react'
import SummaryBar from '../components/plan/SummaryBar'
import ProfileSwitcher from '../components/plan/ProfileSwitcher'
import ActiveWorkView from '../components/plan/ActiveWorkView'
import DependencyGraphView from '../components/plan/DependencyGraphView'
import IssueDependencyGraphView from '../components/plan/IssueDependencyGraphView'
import CharacterizationBanner from '../components/plan/CharacterizationBanner'
import WhyThisOrder from '../components/plan/WhyThisOrder'
import ItemTracesPanel from '../components/plan/ItemTracesPanel'
import IssueDetailModal from '../components/workmap/IssueDetailModal'
import EmptyState from '../components/common/EmptyState'
import InlineHint, { PageSubtitle } from '../components/common/InlineHint'
import usePlanSummary from '../hooks/usePlanSummary'
import useBucketTree from '../hooks/useBucketTree'
import useCharacterizationStatuses from '../hooks/useCharacterizationStatuses'
import { useProjectContext } from '../contexts/ProjectContext'
import { getOrchestratorStatus, pauseOrchestrator, resumeOrchestrator } from '../api/orchestrator'
import './ExecutionPlanPage.css'

function ExecutionPlanPage() {
  const { activeProject } = useProjectContext()
  const activeProjectId = activeProject?.project_id || null
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [tracesItem, setTracesItem] = useState(null)
  const [viewMode, setViewMode] = useState('list')
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)

  // Fetch pause state on mount and periodically
  useEffect(() => {
    let cancelled = false
    const fetchStatus = () => {
      getOrchestratorStatus()
        .then(status => { if (!cancelled) setPaused(!!status?.paused) })
        .catch(() => {})
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 15000)
    return () => { cancelled = true; clearInterval(interval) }
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

  const {
    data,
    loading,
    error,
    refresh
  } = usePlanSummary(activeProjectId)

  const { itemBucketMap, buckets: bucketList } = useBucketTree(activeProjectId)

  const {
    statusMap: charStatusMap,
    loading: charLoading,
  } = useCharacterizationStatuses(activeProjectId)

  const handleItemClick = (item) => {
    setSelectedIssue(item)
  }

  const handleItemTracesClick = (item) => {
    setTracesItem(item)
  }

  const handleDetailSuccess = () => {
    refresh()
  }

  // Show project selection prompt if no project selected
  if (!activeProjectId) {
    return (
      <div className="page">
        <header className="page-header">
          <div className="header-content">
            <h1 className="page-title">Plan</h1>
            <PageSubtitle>System-managed view of active and scheduled work</PageSubtitle>
          </div>
        </header>
        <EmptyState
          icon={FolderOpen}
          title="Select a Project"
          description="Please select a project from the sidebar to view the plan."
        />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div className="header-content">
          <h1 className="page-title">Plan</h1>
          <PageSubtitle>What is running now, what is queued, and why in this order</PageSubtitle>
          <div className="plan-header-controls">
            <ProfileSwitcher
              projectId={activeProjectId}
              activePreset={data?.active_preset}
              activePresetLabel={data?.active_preset_label}
              activePresetColor={data?.active_preset_color}
              onPresetChange={refresh}
            />
            <button
              className={`plan-pause-btn ${paused ? 'plan-pause-btn--paused' : ''}`}
              onClick={togglePause}
              disabled={pauseLoading}
              title={paused ? 'Resume work dispatch' : 'Pause work dispatch'}
            >
              {paused ? <Play size={14} /> : <Pause size={14} />}
              <span>{paused ? 'Resume' : 'Pause'}</span>
            </button>
            <div className="plan-view-toggle">
              <button
                className={`plan-view-btn ${viewMode === 'list' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('list')}
                title="List View"
              >
                <List size={16} />
              </button>
              <button
                className={`plan-view-btn ${viewMode === 'graph' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('graph')}
                title="Directives View"
              >
                <Layers size={16} />
              </button>
              <button
                className={`plan-view-btn ${viewMode === 'deps' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('deps')}
                title="Issue Dependency Graph"
              >
                <Network size={16} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      <InlineHint hintKey="plan-read-only">
        The execution order is determined automatically based on directive priorities, dependencies, and active profiles.
        To influence what gets worked on, adjust priorities in the Backlog or issue a new Directive.
      </InlineHint>

      <SummaryBar data={data} loading={loading} />

      {paused && (
        <div className="plan-paused-banner">
          <Pause size={14} />
          <span>Work dispatch is paused. In-flight work will complete, but no new work will be assigned.</span>
          <button className="plan-paused-resume" onClick={togglePause} disabled={pauseLoading}>
            Resume
          </button>
        </div>
      )}

      <CharacterizationBanner statusMap={charStatusMap} loading={charLoading} />

      {viewMode === 'list' && (
        <ActiveWorkView
          data={data}
          loading={loading}
          onItemClick={handleItemClick}
          onItemTracesClick={handleItemTracesClick}
          itemBucketMap={itemBucketMap}
        />
      )}
      {viewMode === 'graph' && (
        <DependencyGraphView
          data={data}
          loading={loading}
        />
      )}
      {viewMode === 'deps' && (
        <IssueDependencyGraphView
          data={data}
          loading={loading}
        />
      )}

      <WhyThisOrder
        buckets={bucketList}
        traces={data?.recent_traces || []}
        traceCount={data?.trace_count || 0}
        activityEvents={data?.activity_events || []}
      />

      {tracesItem && (
        <ItemTracesPanel
          projectId={activeProjectId}
          item={tracesItem}
          onClose={() => setTracesItem(null)}
        />
      )}

      <IssueDetailModal
        isOpen={Boolean(selectedIssue)}
        onClose={() => setSelectedIssue(null)}
        issue={selectedIssue}
        onSuccess={handleDetailSuccess}
        viewOnly
      />
    </div>
  )
}

export default ExecutionPlanPage
