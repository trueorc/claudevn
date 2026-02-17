import { useState, useCallback, useEffect, useRef } from 'react'
import { getNotifications, getUnreadCount, markNotificationRead, markAllNotificationsRead } from '../api/notifications'

const POLL_INTERVAL_MS = 15000

/**
 * Hook for notification data with polling.
 *
 * @param {string} projectId - Active project ID
 * @param {Object} options - { pollInterval }
 */
function useNotifications(projectId, options = {}) {
  const { pollInterval = POLL_INTERVAL_MS } = options

  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const pollRef = useRef(null)

  const fetchNotifications = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getNotifications(projectId, { limit: 30 })
      setNotifications(data.items || [])
      setUnreadCount(data.unread_count || 0)
    } catch {
      // Silently handle - notifications are non-critical
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await getUnreadCount(projectId)
      setUnreadCount(data.unread_count || 0)
    } catch {
      // Silently handle
    }
  }, [projectId])

  const markRead = useCallback(async (notificationId) => {
    try {
      await markNotificationRead(notificationId)
      setNotifications(prev =>
        prev.map(n => n.notification_id === notificationId ? { ...n, read: true } : n)
      )
      setUnreadCount(prev => Math.max(0, prev - 1))
    } catch {
      // Silently handle
    }
  }, [])

  const markAllRead = useCallback(async () => {
    try {
      await markAllNotificationsRead(projectId)
      setNotifications(prev => prev.map(n => ({ ...n, read: true })))
      setUnreadCount(0)
    } catch {
      // Silently handle
    }
  }, [projectId])

  useEffect(() => {
    fetchNotifications()

    if (pollInterval > 0) {
      pollRef.current = setInterval(fetchUnreadCount, pollInterval)
      return () => clearInterval(pollRef.current)
    }
  }, [fetchNotifications, fetchUnreadCount, pollInterval])

  return {
    notifications,
    unreadCount,
    loading,
    refresh: fetchNotifications,
    markRead,
    markAllRead,
  }
}

export default useNotifications
