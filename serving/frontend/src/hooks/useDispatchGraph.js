/**
 * Hook for the execution dependency graph.
 *
 * Loads graph data from GET /dispatch/graph on mount, then
 * patches node status locally as SSE events arrive — no
 * re-fetching per event.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getDispatchGraph } from '../api/dispatch'

export default function useDispatchGraph(projectId) {
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [criticalPath, setCriticalPath] = useState([])
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  const load = useCallback(async () => {
    if (!projectId) {
      setNodes([])
      setEdges([])
      setCriticalPath([])
      return
    }

    setLoading(true)
    try {
      const data = await getDispatchGraph(projectId)
      if (!mountedRef.current) return
      setNodes(data?.nodes || [])
      setEdges(data?.edges || [])
      setCriticalPath(data?.critical_path || [])
    } catch {
      if (!mountedRef.current) return
      setNodes([])
      setEdges([])
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    mountedRef.current = true
    load()
    return () => { mountedRef.current = false }
  }, [load])

  /**
   * Patch a node's status from an SSE event.
   * Called by the page-level onEvent callback.
   */
  const patchNodeStatus = useCallback((workUnitId, updates) => {
    setNodes(prev => prev.map(n =>
      n.id === workUnitId ? { ...n, ...updates } : n
    ))
  }, [])

  /**
   * Handle an SSE execution event — patches the graph locally.
   */
  const handleEvent = useCallback((event) => {
    const unitId = event.work_unit_id || event.unit_id
    if (!unitId) return

    switch (event.event) {
      case 'work_unit.state_transition':
        // Canonical state machine event — update to new state directly
        if (event.unit_id) {
          patchNodeStatus(event.unit_id, {
            status: event.new_state,
            instance_id: event.compute_id || undefined,
          })
        }
        break
      case 'execution.queued':
        patchNodeStatus(unitId, { status: 'queued' })
        break
      case 'execution.started':
        patchNodeStatus(unitId, {
          status: 'executing',
          instance_id: event.instance_id,
          started_at: event.timestamp,
        })
        break
      case 'execution.completed':
        patchNodeStatus(unitId, {
          status: 'completed',
          completed_at: event.timestamp,
        })
        break
      case 'execution.failed':
        patchNodeStatus(unitId, { status: 'failed' })
        break
      case 'decomposition.approved':
        load()
        break
    }
  }, [patchNodeStatus, load])

  return {
    nodes,
    edges,
    criticalPath,
    loading,
    refresh: load,
    handleEvent,
  }
}
