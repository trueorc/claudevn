import { request } from './index.js'

export async function getSessions(status = null) {
  const params = status ? `?status=${status}` : ''
  const response = await request(`/sessions${params}`)
  return response.sessions || []
}

export async function getSession(sessionId) {
  return request(`/sessions/${sessionId}`)
}

export async function createSession(data) {
  return request('/sessions', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export async function updateSession(sessionId, data) {
  return request(`/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  })
}

// Process maps
export async function getProcessMap(sessionId) {
  return request(`/process-maps/sessions/${sessionId}/map`)
}

export async function createProcessMap(sessionId, businessGoal) {
  return request(`/process-maps/sessions/${sessionId}/map`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, business_goal: businessGoal })
  })
}

export async function getProcessMapProgress(sessionId) {
  return request(`/process-maps/sessions/${sessionId}/map/progress`)
}

// System health
export async function getSystemHealth() {
  return request('/health')
}
