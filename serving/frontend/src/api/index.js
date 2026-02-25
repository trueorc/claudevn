/**
 * API client for ClaudeVN Serving
 */

export const API_BASE = '/api/v1'

export async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `Request failed: ${response.statusText}`)
  }

  // Handle 204 No Content responses
  if (response.status === 204) {
    return null
  }

  return response.json()
}

export * from './compute.js'
export * from './marketplace.js'
export * from './work.js'
export * from './workmap.js'
export * from './projects.js'
export * from './sessions.js'
export * from './spawner.js'
export * from './goals.js'
export * from './notifications.js'
export * from './characterization.js'
export * from './planSummary.js'
export * from './directives.js'
export * from './users.js'
export * from './sshKeys.js'
