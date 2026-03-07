import { request } from './index.js'

/**
 * Load conversation history for a project.
 *
 * @param {string} projectId
 * @param {{ limit?: number, before?: string }} options
 */
export async function getConversation(projectId, { limit = 50, before = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (before) params.set('before', before)
  return request(`/projects/${encodeURIComponent(projectId)}/conversation?${params}`)
}

/**
 * Persist a message to the server-side conversation log.
 *
 * @param {string} projectId
 * @param {{ type?: string, content: string, metadata?: object }} message
 */
export async function sendMessage(projectId, { type = 'user', content, metadata = {} }) {
  return request(`/projects/${encodeURIComponent(projectId)}/conversation`, {
    method: 'POST',
    body: JSON.stringify({ type, content, metadata }),
  })
}

/**
 * Clear the server-side conversation history for a project.
 *
 * @param {string} projectId
 */
export async function clearConversation(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/conversation`, {
    method: 'DELETE',
  })
}
