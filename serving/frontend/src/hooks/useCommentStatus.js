/**
 * useCommentStatus - Hook for real-time comment evaluation status updates.
 *
 * Subscribes to WebSocket events for a specific goal's comment evaluation
 * status changes and provides callbacks for updating comment state.
 */

import { useEffect, useCallback, useRef } from 'react'
import useObservability from './useObservability'

/**
 * Hook to subscribe to comment evaluation status updates for a goal.
 *
 * @param {string} goalId - The goal ID to subscribe to status updates for
 * @param {Function} onStatusChange - Callback when a comment's status changes
 *   Receives (commentId, newStatus, oldStatus, evaluationResult)
 * @param {Object} options - Configuration options
 * @param {boolean} options.autoConnect - Auto-connect to WebSocket (default: true)
 */
function useCommentStatus(goalId, onStatusChange, options = {}) {
  const { autoConnect = true } = options

  const {
    connected,
    connecting,
    latestEvent,
    connect,
    disconnect,
    subscribe,
    unsubscribe
  } = useObservability({ autoConnect })

  // Track the last processed event to avoid duplicate handling
  const lastEventRef = useRef(null)

  // Subscribe to goal-specific events when goalId changes
  useEffect(() => {
    if (goalId && connected) {
      // Subscribe using goal_id as session_id (per backend design)
      subscribe(goalId)

      return () => {
        unsubscribe(goalId)
      }
    }
  }, [goalId, connected, subscribe, unsubscribe])

  // Handle incoming comment_evaluation_status events
  useEffect(() => {
    if (!latestEvent || latestEvent === lastEventRef.current) {
      return
    }

    // Check if this is a comment evaluation status event
    if (latestEvent.type !== 'comment_evaluation_status') {
      return
    }

    const eventData = latestEvent.data
    if (!eventData) {
      return
    }

    // Verify the event is for the goal we're watching
    // session_id in the event is the goal_id
    if (eventData.session_id !== goalId) {
      return
    }

    lastEventRef.current = latestEvent

    // Call the status change callback
    if (onStatusChange) {
      onStatusChange(
        eventData.comment_id,
        eventData.new_status,
        eventData.old_status,
        {
          commentType: eventData.comment_type,
          confidence: eventData.confidence,
          summary: eventData.summary,
          error: eventData.error
        }
      )
    }
  }, [latestEvent, goalId, onStatusChange])

  // Manual connection control
  const manualConnect = useCallback(() => {
    connect()
    if (goalId) {
      // Small delay to ensure connection is established
      setTimeout(() => subscribe(goalId), 100)
    }
  }, [connect, subscribe, goalId])

  const manualDisconnect = useCallback(() => {
    if (goalId) {
      unsubscribe(goalId)
    }
    disconnect()
  }, [disconnect, unsubscribe, goalId])

  return {
    connected,
    connecting,
    connect: manualConnect,
    disconnect: manualDisconnect
  }
}

export default useCommentStatus
