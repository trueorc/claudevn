import { request } from './index.js'

/**
 * Send a presence heartbeat for a project.
 *
 * @param {string} projectId
 * @param {{ current_view?: string }} options
 */
export async function sendHeartbeat(projectId, { current_view = null } = {}) {
  return request(`/projects/${encodeURIComponent(projectId)}/presence/heartbeat`, {
    method: 'POST',
    body: JSON.stringify({ current_view }),
  })
}

/**
 * Fetch active users for a project.
 *
 * @param {string} projectId
 * @returns {Promise<{ users: Array }>}
 */
export async function getPresence(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/presence`)
}
