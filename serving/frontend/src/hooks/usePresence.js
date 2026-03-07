import { useState, useEffect, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import ObservabilityWebSocket from '../services/observabilityWebSocket'
import { sendHeartbeat, getGlobalPresence } from '../api/presence'

// Shared singleton WebSocket instance
let _ws = null
function getWebSocket() {
  if (!_ws) {
    _ws = new ObservabilityWebSocket('/api/v1/observability/stream')
    _ws.connect()
  }
  return _ws
}

// Readable labels for URL path segments
const VIEW_LABELS = {
  dashboard: 'Dashboard',
  backlog: 'Backlog',
  plan: 'Plan',
  directives: 'Goals',
  projects: 'Projects',
  marketplace: 'Marketplace',
  network: 'Network',
  timing: 'Timing',
  notifications: 'Notifications',
  settings: 'Settings',
}

/**
 * Extract a human-readable view label from the current pathname.
 * Handles nested routes like /settings/profile → "Settings".
 */
function viewFromPath(pathname) {
  if (!pathname) return 'Dashboard'
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length === 0) return 'Dashboard'
  const primary = segments[0]
  return VIEW_LABELS[primary] || primary.charAt(0).toUpperCase() + primary.slice(1)
}

/**
 * Track user presence globally across all projects.
 *
 * Sends a heartbeat every 30 s with the current route and project name,
 * listens for WebSocket ``presence_update`` events, and falls back to
 * polling GET /presence every 30 s when the WebSocket is unavailable.
 *
 * @param {string|null} projectId    Active project ID (or null when none selected)
 * @param {string|null} projectName  Active project name (for display in activity label)
 * @returns {{ users: Array, sendHeartbeat: Function }}
 */
export default function usePresence(projectId, projectName) {
  const [users, setUsers] = useState([])
  const location = useLocation()
  const currentView = viewFromPath(location.pathname)
  const pollTimerRef = useRef(null)
  const heartbeatTimerRef = useRef(null)

  // ------------------------------------------------------------------
  // Fetch global presence list (used for initial load and fallback poll)
  // ------------------------------------------------------------------
  const fetchPresence = useCallback(async () => {
    try {
      const data = await getGlobalPresence()
      if (data?.users) setUsers(data.users)
    } catch (err) {
      // Non-critical — ignore silently
    }
  }, [])

  // ------------------------------------------------------------------
  // Send heartbeat (requires a project to be selected)
  // ------------------------------------------------------------------
  const doHeartbeat = useCallback(async () => {
    if (!projectId) return
    try {
      await sendHeartbeat(projectId, {
        current_view: currentView,
        project_name: projectName || null,
      })
    } catch (err) {
      // Non-critical — ignore silently
    }
  }, [projectId, currentView, projectName])

  // ------------------------------------------------------------------
  // WebSocket listener for presence_update events (global)
  // ------------------------------------------------------------------
  useEffect(() => {
    const ws = getWebSocket()

    const handlePresenceUpdate = (eventData) => {
      if (!eventData) return
      if (Array.isArray(eventData.users)) {
        setUsers(eventData.users)
      }
    }

    ws.on('presence_update', handlePresenceUpdate)

    return () => {
      ws.off('presence_update', handlePresenceUpdate)
    }
  }, [])

  // ------------------------------------------------------------------
  // Heartbeat timer — fires every 30 s, also on view/project change
  // ------------------------------------------------------------------
  useEffect(() => {
    // Always fetch presence (global) even without a project
    fetchPresence()

    // Only send heartbeats when a project is active
    if (projectId) {
      doHeartbeat()
      heartbeatTimerRef.current = setInterval(doHeartbeat, 30_000)
    }

    pollTimerRef.current = setInterval(fetchPresence, 30_000)

    return () => {
      clearInterval(heartbeatTimerRef.current)
      clearInterval(pollTimerRef.current)
    }
  }, [projectId, currentView, projectName, doHeartbeat, fetchPresence])

  return { users, sendHeartbeat: doHeartbeat }
}
