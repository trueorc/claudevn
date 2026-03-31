/**
 * Dispatch API client — Layer 2 execution observability and control.
 */

import { request } from './index.js'

export async function getDispatchGraph(projectId) {
  return request(`/dispatch/graph?project_id=${encodeURIComponent(projectId)}`)
}

export async function getDispatchTiming(projectId) {
  return request(`/dispatch/timing?project_id=${encodeURIComponent(projectId)}`)
}

export async function getDispatchQueue(projectId) {
  return request(`/dispatch/queue?project_id=${encodeURIComponent(projectId)}`)
}

export async function getActiveExecutions(projectId) {
  return request(`/dispatch/active?project_id=${encodeURIComponent(projectId)}`)
}

export async function getDispatchStatus() {
  return request('/dispatch/status')
}

export async function pauseDispatcher() {
  return request('/dispatch/pause', { method: 'POST' })
}

export async function resumeDispatcher() {
  return request('/dispatch/resume', { method: 'POST' })
}

export async function getActivityLog(projectId, limit = 200) {
  return request(`/dispatch/activity-log?project_id=${encodeURIComponent(projectId)}&limit=${limit}`)
}
