import { useState, useEffect, useCallback, useMemo } from 'react'
import { FolderOpen, Pause, Play, RefreshCw } from 'lucide-react'
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
import { getDispatchStatus, pauseDispatcher, resumeDispatcher, getActivityLog } from '../api/dispatch'
import './ExecutionPlanPage.css'

function ExecutionPlanPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)

  // Activity log — loaded from Redis on mount, updated by SSE in real-time
  const [activityEvents, setActivityEvents] = useState([])
  const [stuckItems, setStuckItems] = useState([])

  // Load persisted activity log on mount (survives page navigation)
  useEffect(() => {
    if (!projectId) return
    getActivityLog(projectId).then(data => {
      if (data?.events) {
        setActivityEvents(data.events)
        // Extract stuck items from persisted events
        const stuck = data.events
          .filter(e => e.new_state === 'failed' || e.new_state === 'merge_conflict')
          .map(e => ({
            type: e.new_state === 'failed' ? 'failed' : 'stuck',
            work_unit_id: e.unit_id,
            description: e.reason || `Unit ${e.new_state}`,
            id: e.unit_id,
          }))
        if (stuck.length > 0) setStuckItems(stuck)
      }
    }).catch(() => {})
  }, [projectId])

  // Graph data (REST + SSE patching)
  const { nodes, edges, criticalPath, loading: graphLoading, handleEvent: patchGraph, refresh: refreshGraph } = useDispatchGraph(projectId)

  // Summary counts
  const { data: summaryData, loading: summaryLoading } = usePlanSummary(projectId)

  // Timing
  const { timing } = useDispatchTiming(projectId)

  // Build timing lookup for graph nodes
  const timingMap = useMemo(() => {
    if (!timing?.per_unit) return {}
    const map = {}
    for (const entry of timing.per_unit) {
      if (entry.exec_duration_ms != null) {
        map[entry.id] = entry.exec_duration_ms
      }
    }
    return map
  }, [timing])

  // SSE subscription — patches graph + feeds activity log
  useEventStream({
    patterns: ['execution.*', 'verification.*', 'decomposition.*', 'compute.*', 'work.*', 'work_unit.*', 'error.*'],
    projectId,
    enabled: !!projectId,
    onEvent: useCallback((event) => {
      // Activity log
      setActivityEvents(prev => [event, ...prev].slice(0, 500))

      // Patch the graph
      patchGraph(event)

      // Detect failures for stuck work (deduplicate by unit_id)
      const failUnitId = event.work_unit_id || event.unit_id
      if (event.event === 'execution.failed' || (event.event === 'work_unit.state_transition' && event.new_state === 'failed')) {
        setStuckItems(prev => {
          if (prev.some(i => (i.id || i.work_unit_id) === failUnitId)) return prev
          return [...prev, {
            type: 'failed',
            work_unit_id: failUnitId,
            description: event.reason || `Unit failed`,
            reason: event.reason,
            id: failUnitId,
          }]
        })
      }
      // Clear items when units recover (retried, completed, etc.)
      if (event.event === 'work_unit.state_transition' && ['queued', 'executing', 'completed'].includes(event.new_state)) {
        const recoveredId = event.unit_id
        if (recoveredId) {
          setStuckItems(prev => prev.filter(i => (i.id || i.work_unit_id) !== recoveredId))
        }
      }
    }, [patchGraph]),
  })

  // Manual refresh — reloads graph, activity log, stuck items from server
  const [refreshing, setRefreshing] = useState(false)
  const handleRefresh = useCallback(async () => {
    if (!projectId) return
    setRefreshing(true)
    try {
      refreshGraph()
      const data = await getActivityLog(projectId)
      if (data?.events) {
        setActivityEvents(data.events)
        const stuck = data.events
          .filter(e => e.new_state === 'failed' || e.new_state === 'merge_conflict')
          .map(e => ({
            type: e.new_state === 'failed' ? 'failed' : 'stuck',
            work_unit_id: e.unit_id,
            description: e.reason || `Unit ${e.new_state}`,
            id: e.unit_id,
          }))
        setStuckItems(stuck)
      }
    } catch (e) {
      // ignore
    } finally {
      setRefreshing(false)
    }
  }, [projectId, refreshGraph])

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

  const activeCount = nodes.filter(n =>
    ['executing', 'submitted', 'merging', 'verifying'].includes(n.status)
  ).length
  const mergingCount = nodes.filter(n =>
    ['merging', 'merge_conflict'].includes(n.status)
  ).length
  const queuedCount = queuedNodes.length
  const completedCount = nodes.filter(n => n.status === 'completed' || n.status === 'verified').length
  const failedCount = nodes.filter(n => n.status === 'failed' || n.status === 'failed_verification' || n.status === 'merge_conflict').length
  const blockedCount = nodes.filter(n => {
    const deps = n.depends_on || []
    return deps.length > 0 && n.status === 'ready' && deps.some(d => {
      const dep = nodes.find(nn => nn.id === d)
      return dep && dep.status !== 'completed' && dep.status !== 'verified'
    })
  }).length

  // Build SummaryBar-compatible data from graph nodes
  const graphSummaryData = {
    in_progress_count: activeCount,
    merging_count: mergingCount,
    ready_count: queuedCount,
    blocked_count: blockedCount,
    failed_count: failedCount,
    done_count: completedCount,
    total_count: nodes.length,
  }

  return (
    <div className="exec-page">
      <header className="exec-header">
        <div className="exec-header-content">
          <h1>Execution</h1>
          <PageSubtitle>
            {activeProject?.name} — {activeCount} active, {queuedCount} queued, {completedCount} done
          </PageSubtitle>
        </div>
        <div className="exec-header-actions">
          <button
            className="exec-refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh all data"
          >
            <RefreshCw size={14} className={refreshing ? 'exec-spin' : ''} />
          </button>
          <button
            className={`exec-pause-btn ${paused ? 'exec-pause-btn--paused' : ''}`}
            onClick={togglePause}
            disabled={pauseLoading}
            title={paused ? 'Resume dispatch' : 'Pause dispatch'}
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
            <span>{paused ? 'Resume' : 'Pause'}</span>
          </button>
        </div>
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
            timingMap={timingMap}
          />
          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              onClose={() => setSelectedNodeId(null)}
              onAction={() => { refreshGraph(); setSelectedNodeId(null) }}
            />
          )}
        </div>

        {/* Right: Sidebar panels */}
        <div className="exec-sidebar">
          <SummaryBar data={graphSummaryData} loading={graphLoading} />

          <StuckWorkDetector
            items={stuckItems}
            projectId={projectId}
            onDismiss={(id) => {
              if (id === 'all') setStuckItems([])
              else setStuckItems(prev => prev.filter(i => (i.id || i.work_unit_id) !== id))
            }}
            onAction={() => refreshGraph()}
          />

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
