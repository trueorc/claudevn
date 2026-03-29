/**
 * React hook for subscribing to the v2.0 SSE event stream.
 * Replaces all polling patterns (useIssues pollInterval, usePlanSummary pollInterval, etc.)
 *
 * Usage:
 *   const { events, connected } = useEventStream({
 *     patterns: ['decomposition.*', 'verification.*'],
 *     onEvent: (event) => { ... },
 *   })
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { connectEventStream } from '../api/events'

export default function useEventStream({ patterns = ['*'], onEvent, enabled = true } = {}) {
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)
  const connectionRef = useRef(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!enabled) return

    const clientId = `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

    // Build wildcard handler that routes all events
    const handlers = {
      '*': (data) => {
        setLastEvent(data)
        if (onEventRef.current) {
          onEventRef.current(data)
        }
      },
    }

    // Also register specific pattern handlers so EventSource
    // can match named events (e.g., "decomposition.updated")
    const specificHandler = (data) => {
      setLastEvent(data)
      if (onEventRef.current) {
        onEventRef.current(data)
      }
    }

    // Register handlers for known event types
    const eventNames = [
      'decomposition.started', 'decomposition.updated', 'decomposition.approved', 'decomposition.feedback',
      'execution.queued', 'execution.started', 'execution.completed', 'execution.failed',
      'verification.started', 'verification.completed', 'verification.failed', 'verification.integration_conflict',
      'system.health', 'system.presence',
    ]
    eventNames.forEach(name => { handlers[name] = specificHandler })

    const conn = connectEventStream(patterns, handlers, clientId)
    connectionRef.current = conn

    conn.source.onopen = () => setConnected(true)
    conn.source.onerror = () => setConnected(false)

    return () => {
      conn.close()
      connectionRef.current = null
      setConnected(false)
    }
  }, [patterns.join(','), enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return { connected, lastEvent }
}
