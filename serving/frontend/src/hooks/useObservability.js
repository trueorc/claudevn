import { useState, useEffect, useRef, useCallback } from 'react'
import ObservabilityWebSocket from '../services/observabilityWebSocket'

function useObservability(options = {}) {
  const { autoConnect = true } = options

  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [events, setEvents] = useState([])
  const [latestEvent, setLatestEvent] = useState(null)

  const connect = useCallback(() => {
    if (!wsRef.current) {
      wsRef.current = new ObservabilityWebSocket()

      wsRef.current.on('connected', () => {
        setConnected(true)
        setConnecting(false)
      })

      wsRef.current.on('disconnected', () => {
        setConnected(false)
        setConnecting(false)
      })

      const eventTypes = [
        'activity_state_change',
        'exchange',
        'process_map_reevaluation',
        'blocker_identified',
        'work_status_change',
        'compute_registered',
        'compute_deregistered',
        'comment_evaluation_status',
        'goal_processing_stage'
      ]

      eventTypes.forEach(eventType => {
        wsRef.current.on(eventType, (eventData) => {
          const event = {
            type: eventType,
            data: eventData,
            timestamp: new Date().toISOString()
          }
          setEvents(prev => [...prev.slice(-99), event])
          setLatestEvent(event)
        })
      })
    }

    setConnecting(true)
    wsRef.current.connect()
  }, [])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.disconnect()
      setConnected(false)
      setConnecting(false)
    }
  }, [])

  const subscribe = useCallback((sessionIds) => {
    if (wsRef.current) {
      wsRef.current.subscribe(sessionIds)
    }
  }, [])

  const unsubscribe = useCallback((sessionIds) => {
    if (wsRef.current) {
      wsRef.current.unsubscribe(sessionIds)
    }
  }, [])

  const clearEvents = useCallback(() => {
    setEvents([])
    setLatestEvent(null)
  }, [])

  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect()
      }
    }
  }, [autoConnect, connect])

  return {
    connected,
    connecting,
    events,
    latestEvent,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearEvents
  }
}

export default useObservability
