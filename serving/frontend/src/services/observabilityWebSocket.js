/**
 * WebSocket client for real-time observability events.
 */

class ObservabilityWebSocket {
  constructor(url = '/api/v1/observability/stream') {
    // Convert relative path to WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.url = url.startsWith('ws') ? url : `${protocol}//${window.location.host}${url}`
    this.ws = null
    this.subscribers = new Map()
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 10
    this.reconnectDelay = 1000
    this.isConnecting = false
    this.isIntentionallyClosed = false
    this.subscribedSessions = new Set()
  }

  connect() {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
      return
    }

    this.isConnecting = true
    this.isIntentionallyClosed = false

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this.isConnecting = false
        this.reconnectAttempts = 0
        this.reconnectDelay = 1000

        if (this.subscribedSessions.size > 0) {
          this.subscribe(Array.from(this.subscribedSessions))
        }

        this._notifySubscribers('connected', { status: 'connected' })
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          const { type, event: eventData } = data
          this._notifySubscribers(type, eventData)
        } catch (error) {
          console.error('[WS] Parse error:', error)
        }
      }

      this.ws.onclose = (event) => {
        this.isConnecting = false
        this._notifySubscribers('disconnected', { status: 'disconnected', code: event.code })

        if (!this.isIntentionallyClosed) {
          this.reconnect()
        }
      }

      this.ws.onerror = () => {
        this.isConnecting = false
      }
    } catch (error) {
      this.isConnecting = false
      this.reconnect()
    }
  }

  reconnect() {
    if (this.isIntentionallyClosed) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this._notifySubscribers('error', { message: 'Max reconnect attempts reached' })
      return
    }

    this.reconnectAttempts++
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000)

    setTimeout(() => {
      if (!this.isIntentionallyClosed) {
        this.connect()
      }
    }, delay)
  }

  subscribe(sessionIds) {
    const ids = Array.isArray(sessionIds) ? sessionIds : [sessionIds]
    ids.forEach(id => this.subscribedSessions.add(id))

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'subscribe', session_ids: ids }))
    }
  }

  unsubscribe(sessionIds) {
    const ids = Array.isArray(sessionIds) ? sessionIds : [sessionIds]
    ids.forEach(id => this.subscribedSessions.delete(id))

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'unsubscribe', session_ids: ids }))
    }
  }

  /**
   * Send a message to the server.
   * @param {object} message - The message object (must include an 'action' field)
   */
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  on(eventType, callback) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, [])
    }
    this.subscribers.get(eventType).push(callback)
  }

  off(eventType, callback) {
    if (this.subscribers.has(eventType)) {
      const callbacks = this.subscribers.get(eventType)
      const index = callbacks.indexOf(callback)
      if (index > -1) {
        callbacks.splice(index, 1)
      }
    }
  }

  _notifySubscribers(eventType, eventData) {
    if (this.subscribers.has(eventType)) {
      this.subscribers.get(eventType).forEach(callback => {
        try {
          callback(eventData)
        } catch (error) {
          console.error(`[WS] Callback error for ${eventType}:`, error)
        }
      })
    }
  }

  disconnect() {
    this.isIntentionallyClosed = true
    this.subscribedSessions.clear()

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN
  }
}

export default ObservabilityWebSocket
