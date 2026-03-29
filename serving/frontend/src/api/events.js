/**
 * SSE event stream API for v2.0 real-time updates.
 * Replaces all polling patterns with push-based event delivery.
 */

import { API_BASE } from './index.js'

/**
 * Connect to the SSE event stream.
 * @param {string[]} patterns - Event patterns to subscribe to (e.g., ["decomposition.*", "verification.*"])
 * @param {object} handlers - Map of event name to handler function
 * @param {string} clientId - Unique client identifier
 * @returns {{ close: () => void }} - Call close() to disconnect
 */
export function connectEventStream(patterns = ['*'], handlers = {}, clientId = '') {
  const params = new URLSearchParams()
  patterns.forEach(p => params.append('pattern', p))
  if (clientId) params.append('client_id', clientId)

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

  // Generic message handler for unregistered events
  eventSource.onmessage = (event) => {
    if (handlers['*']) {
      try {
        const data = JSON.parse(event.data)
        handlers['*'](data)
      } catch { /* keepalive or unparseable */ }
    }
  }

  eventSource.onerror = () => {
    // EventSource auto-reconnects; log for debugging
    console.debug('SSE connection error, will auto-reconnect')
  }

  return {
    close: () => eventSource.close(),
    source: eventSource,
  }
}
