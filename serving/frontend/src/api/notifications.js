import { request } from './index.js'

export async function getNotifications(projectId = null, options = {}) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  if (options.unreadOnly) params.append('unread_only', 'true')
  if (options.limit) params.append('limit', String(options.limit))
  const qs = params.toString()
  return request(`/notifications${qs ? `?${qs}` : ''}`)
}

export async function getUnreadCount(projectId = null) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  const qs = params.toString()
  return request(`/notifications/unread-count${qs ? `?${qs}` : ''}`)
}

export async function markNotificationRead(notificationId) {
  return request(`/notifications/${notificationId}/read`, { method: 'POST' })
}

export async function markAllNotificationsRead(projectId = null) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  const qs = params.toString()
  return request(`/notifications/read-all${qs ? `?${qs}` : ''}`, { method: 'POST' })
}
