/**
 * React hook for subscribing to the v2.0 SSE event stream.
 * Replaces all polling patterns. Project-scoped — only receives
 * events for the specified project.
 *
 * Usage:
 *   const { connected } = useEventStream({
 *     patterns: ['decomposition.*', 'verification.*'],
 *     projectId: activeProject?.project_id,
 *     onEvent: (event) => { ... },
 *   })
 */

import { useState, useEffect, useRef } from 'react'
import { connectEventStream } from '../api/events'

export default function useEventStream({ patterns = ['*'], projectId, onEvent, enabled = true } = {}) {
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)
  const connectionRef = useRef(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!enabled) return

    const clientId = `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

    const handleEvent = (data) => {
      // Client-side project filter as defense-in-depth
      // (server-side filtering is primary, this is a safety net)
      if (projectId && data.project_id && data.project_id !== projectId) {
        return
      }
      setLastEvent(data)
      if (onEventRef.current) {
        onEventRef.current(data)
      }
    }

    const handlers = { '*': handleEvent }

    // Register specific event handlers
    const eventNames = [
      'decomposition.started', 'decomposition.updated', 'decomposition.approved', 'decomposition.feedback',
      'execution.queued', 'execution.started', 'execution.completed', 'execution.failed',
      'verification.started', 'verification.completed', 'verification.failed', 'verification.integration_conflict',
      'work_unit.state_transition',
      'compute.connected', 'compute.disconnected', 'compute.health_changed', 'compute.instance_approved',
      'work.ready_for_dispatch', 'work.stuck_detected',
      'error.mcp_tool', 'error.dispatch', 'error.health_check', 'error.sse_connection',
      'system.health', 'system.presence',
    ]
    eventNames.forEach(name => { handlers[name] = handleEvent })

    // Pass projectId to SSE endpoint for server-side filtering
    const conn = connectEventStream(patterns, handlers, clientId, projectId)
    connectionRef.current = conn

    conn.source.onopen = () => setConnected(true)
    conn.source.onerror = () => setConnected(false)

    return () => {
      conn.close()
      connectionRef.current = null
      setConnected(false)
    }
  }, [patterns.join(','), projectId, enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return { connected, lastEvent }
}
