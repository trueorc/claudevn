import { useState, useEffect, useCallback, useRef } from 'react'
import { getWorkMapStats, getWorkMap, getActiveWork, deriveIssuesByGoal, deriveGraphData } from '../api/workmap'
import useObservability from './useObservability'

function useWorkMap(options = {}) {
  const { pollInterval = 10000, useWebSocket = true, projectId = null } = options

  const [stats, setStats] = useState(null)
  const [issuesByGoal, setIssuesByGoal] = useState([])
  const [activeWork, setActiveWork] = useState([])
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const lastEventRef = useRef(null)

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const load = useCallback(async () => {
    try {
      const [statsData, workmap, activeData] = await Promise.all([
        getWorkMapStats(projectId),
        getWorkMap(projectId),
        getActiveWork(projectId)
      ])
      setStats(statsData)
      setIssuesByGoal(deriveIssuesByGoal(workmap))
      setActiveWork(activeData)
      setGraphData(deriveGraphData(workmap))
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const refresh = useCallback(() => {
    load()
  }, [load])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventType = latestEvent.type

      // Refresh on relevant events
      if (eventType === 'work_status_change' ||
          eventType === 'blocker_identified' ||
          eventType === 'process_map_reevaluation') {
        refresh()
      }
    }
  }, [latestEvent, refresh])

  // Initial load
  useEffect(() => {
    load()
  }, [load])

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    if ((!useWebSocket || !connected) && pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval, connected, useWebSocket])

  return {
    stats,
    issuesByGoal,
    activeWork,
    graphData,
    loading,
    error,
    refresh,
    connected
  }
}

export default useWorkMap
