import { useState, useEffect, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import ObservabilityWebSocket from '../services/observabilityWebSocket'
import { sendHeartbeat, getPresence } from '../api/presence'

// Shared singleton WebSocket instance
let _ws = null
function getWebSocket() {
  if (!_ws) {
    _ws = new ObservabilityWebSocket('/api/v1/observability/stream')
    _ws.connect()
  }
  return _ws
}

// Extract a short view label from the current pathname
function viewFromPath(pathname) {
  if (!pathname) return null
  const segment = pathname.split('/').filter(Boolean)[0]
  return segment || 'dashboard'
}

/**
 * Track user presence for a project.
 *
 * Sends a heartbeat every 30 s with the current route, listens for
 * WebSocket ``presence_update`` events from the server, and falls back
 * to polling GET /presence every 30 s when the WebSocket is unavailable.
 *
 * @param {string|null} projectId  Active project ID (or null when none selected)
 * @returns {{ users: Array, sendHeartbeat: Function }}
 */
export default function usePresence(projectId) {
  const [users, setUsers] = useState([])
  const location = useLocation()
  const currentView = viewFromPath(location.pathname)
  const pollTimerRef = useRef(null)
  const heartbeatTimerRef = useRef(null)

  // ------------------------------------------------------------------
  // Fetch current presence list (used for initial load and fallback poll)
  // ------------------------------------------------------------------
  const fetchPresence = useCallback(async () => {
    if (!projectId) return
    try {
      const data = await getPresence(projectId)
      if (data?.users) setUsers(data.users)
    } catch (err) {
      // Non-critical — ignore silently
    }
  }, [projectId])

  // ------------------------------------------------------------------
  // Send heartbeat
  // ------------------------------------------------------------------
  const doHeartbeat = useCallback(async () => {
    if (!projectId) return
    try {
      await sendHeartbeat(projectId, { current_view: currentView })
    } catch (err) {
      // Non-critical — ignore silently
    }
  }, [projectId, currentView])

  // ------------------------------------------------------------------
  // WebSocket listener for presence_update events
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!projectId) return

    const ws = getWebSocket()

    const handlePresenceUpdate = (eventData) => {
      if (!eventData) return
      // eventData is the raw payload after type stripping in observabilityWebSocket
      // The server sends { project_id, users } as the event body
      if (eventData.project_id === projectId && Array.isArray(eventData.users)) {
        setUsers(eventData.users)
      }
    }

    ws.on('presence_update', handlePresenceUpdate)

    return () => {
      ws.off('presence_update', handlePresenceUpdate)
    }
  }, [projectId])

  // ------------------------------------------------------------------
  // Heartbeat timer — fires every 30 s, also on view change
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!projectId) return

    // Send immediately when project or view changes
    doHeartbeat()
    fetchPresence()

    heartbeatTimerRef.current = setInterval(doHeartbeat, 30_000)
    pollTimerRef.current = setInterval(fetchPresence, 30_000)

    return () => {
      clearInterval(heartbeatTimerRef.current)
      clearInterval(pollTimerRef.current)
    }
  }, [projectId, currentView, doHeartbeat, fetchPresence])

  return { users, sendHeartbeat: doHeartbeat }
}
