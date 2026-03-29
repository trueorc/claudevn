/**
 * SSE event stream API for v2.0 real-time updates.
 * Replaces all polling patterns with push-based event delivery.
 * Project-scoped — pass projectId to only receive events for that project.
 */

import { API_BASE } from './index.js'

/**
 * Connect to the SSE event stream.
 * @param {string[]} patterns - Event patterns to subscribe to
 * @param {object} handlers - Map of event name to handler function
 * @param {string} clientId - Unique client identifier
 * @param {string|null} projectId - Project to scope events to (null = all)
 * @returns {{ close: () => void, source: EventSource }}
 */
export function connectEventStream(patterns = ['*'], handlers = {}, clientId = '', projectId = null) {
  const params = new URLSearchParams()
  patterns.forEach(p => params.append('pattern', p))
  if (clientId) params.append('client_id', clientId)
  if (projectId) params.append('project_id', projectId)

  const url = `${API_BASE}/events/stream?${params.toString()}`
  const eventSource = new EventSource(url)

  // Register handlers for each event type
  Object.entries(handlers).forEach(([eventName, handler]) => {
    eventSource.addEventListener(eventName, (event) => {
      try {
        const data = JSON.parse(event.data)
        handler(data)
      } catch (err) {
        console.error(`Failed to parse event ${eventName}:`, err)
      }
    })
  })

  eventSource.onmessage = (event) => {
    if (handlers['*']) {
      try {
        const data = JSON.parse(event.data)
        handlers['*'](data)
      } catch { /* keepalive or unparseable */ }
    }
  }

  eventSource.onerror = () => {
    console.debug('SSE connection error, will auto-reconnect')
  }

  return {
    close: () => eventSource.close(),
    source: eventSource,
  }
}
