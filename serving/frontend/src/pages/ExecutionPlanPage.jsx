import { useState, useEffect, useCallback, useMemo } from 'react'
import { FolderOpen, Pause, Play } from 'lucide-react'
import ExecutionGraph from '../components/plan/ExecutionGraph'
import NodeDetailPanel from '../components/plan/NodeDetailPanel'
import SummaryBar from '../components/plan/SummaryBar'
import StuckWorkDetector from '../components/plan/StuckWorkDetector'
import QueuePreview from '../components/plan/QueuePreview'
import ActiveComputePanel from '../components/plan/ActiveComputePanel'
import ExecutionTimingPanel from '../components/plan/ExecutionTimingPanel'
import EventActivityLog from '../components/plan/EventActivityLog'
import EmptyState from '../components/common/EmptyState'
import { PageSubtitle } from '../components/common/InlineHint'
import usePlanSummary from '../hooks/usePlanSummary'
import useEventStream from '../hooks/useEventStream'
import useDispatchGraph from '../hooks/useDispatchGraph'
import useDispatchTiming from '../hooks/useDispatchTiming'
import { useProjectContext } from '../contexts/ProjectContext'
import { getDispatchStatus, pauseDispatcher, resumeDispatcher } from '../api/dispatch'
import './ExecutionPlanPage.css'

function ExecutionPlanPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)

  // Live event stream
  const [activityEvents, setActivityEvents] = useState([])
  const [stuckItems, setStuckItems] = useState([])

  // Graph data (REST + SSE patching)
  const { nodes, edges, criticalPath, loading: graphLoading, handleEvent: patchGraph } = useDispatchGraph(projectId)

  // Summary counts
  const { data: summaryData, loading: summaryLoading } = usePlanSummary(projectId)

  // Timing
  const { timing } = useDispatchTiming(projectId)

  // SSE subscription — patches graph + feeds activity log
  useEventStream({
    patterns: ['execution.*', 'verification.*', 'decomposition.*'],
    projectId,
    enabled: !!projectId,
    onEvent: useCallback((event) => {
      // Activity log
      setActivityEvents(prev => [event, ...prev].slice(0, 500))

      // Patch the graph
      patchGraph(event)

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
          description: 'Verification failed',
          reason: event.details || event.failed_checks?.join(', '),
          id: event.work_unit_id,
        }])
      }
    }, [patchGraph]),
  })

  // Fetch dispatch status (paused state)
  useEffect(() => {
    let cancelled = false
    getDispatchStatus()
      .then(status => { if (!cancelled) setPaused(!!status?.paused) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const togglePause = useCallback(async () => {
    setPauseLoading(true)
    try {
      if (paused) {
        await resumeDispatcher()
        setPaused(false)
      } else {
        await pauseDispatcher()
        setPaused(true)
      }
    } catch (err) {
      console.warn('Failed to toggle pause:', err)
    } finally {
      setPauseLoading(false)
    }
  }, [paused])

  // Derive queue preview and active compute from graph nodes
  const queuedNodes = useMemo(
    () => nodes.filter(n => n.status === 'queued' || n.status === 'ready'),
    [nodes]
  )
  const executingNodes = useMemo(
    () => nodes.filter(n => n.status === 'executing'),
    [nodes]
  )

  // Selected node detail
  const selectedNode = useMemo(
    () => nodes.find(n => n.id === selectedNodeId) || null,
    [nodes, selectedNodeId]
  )

  const handleNodeClick = useCallback((nodeId) => {
    setSelectedNodeId(prev => prev === nodeId ? null : nodeId)
  }, [])

  if (!projectId) {
    return (
      <div className="exec-page">
        <header className="exec-header">
          <h1>Execution</h1>
          <PageSubtitle>Select a project to view execution status</PageSubtitle>
        </header>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar to view execution status." />
      </div>
    )
  }

  const activeCount = executingNodes.length
  const queuedCount = queuedNodes.length
  const completedCount = nodes.filter(n => n.status === 'completed' || n.status === 'verified').length

  return (
    <div className="exec-page">
      <header className="exec-header">
        <div className="exec-header-content">
          <h1>Execution</h1>
          <PageSubtitle>
            {activeProject?.name} — {activeCount} active, {queuedCount} queued, {completedCount} done
          </PageSubtitle>
        </div>
        <button
          className={`exec-pause-btn ${paused ? 'exec-pause-btn--paused' : ''}`}
          onClick={togglePause}
          disabled={pauseLoading}
          title={paused ? 'Resume dispatch' : 'Pause dispatch'}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
          <span>{paused ? 'Resume' : 'Pause'}</span>
        </button>
      </header>

      {paused && (
        <div className="exec-paused-banner">
          <Pause size={14} />
          <span>Dispatch is paused. In-flight work will complete, but no new work will be assigned.</span>
          <button className="exec-paused-resume" onClick={togglePause} disabled={pauseLoading}>Resume</button>
        </div>
      )}

      <div className="exec-body">
        {/* Left: Graph */}
        <div className="exec-graph-area">
          <ExecutionGraph
            nodes={nodes}
            edges={edges}
            criticalPath={criticalPath}
            selectedNodeId={selectedNodeId}
            onNodeClick={handleNodeClick}
          />
          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              onClose={() => setSelectedNodeId(null)}
            />
          )}
        </div>

        {/* Right: Sidebar panels */}
        <div className="exec-sidebar">
          <SummaryBar data={summaryData} loading={summaryLoading} />

          <StuckWorkDetector items={stuckItems} />

          <QueuePreview items={queuedNodes} />

          <ActiveComputePanel executions={executingNodes} />

          <ExecutionTimingPanel timing={timing} />

          <EventActivityLog events={activityEvents} />
        </div>
      </div>
    </div>
  )
}

export default ExecutionPlanPage
