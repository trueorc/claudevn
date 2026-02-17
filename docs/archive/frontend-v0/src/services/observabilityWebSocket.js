/**
 * WebSocket client for real-time observability events.
 * 
 * Connects to serving component's WebSocket endpoint and manages
 * session subscriptions for real-time updates.
 */

class ObservabilityWebSocket {
  constructor(url = 'ws://localhost:8002/api/v1/observability/stream') {
    this.url = url;
    this.ws = null;
    this.subscribers = new Map(); // event_type -> [callback functions]
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000; // Start with 1 second
    this.isConnecting = false;
    this.isIntentionallyClosed = false;
    this.subscribedSessions = new Set();
    
    console.log(`[ObservabilityWS] Initialized with URL: ${this.url}`);
  }
  
  /**
   * Connect to WebSocket server.
   */
  connect() {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
      console.log('[ObservabilityWS] Already connecting or connected');
      return;
    }
    
    this.isConnecting = true;
    this.isIntentionallyClosed = false;
    
    console.log('[ObservabilityWS] Connecting...');
    
    try {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('[ObservabilityWS] Connected successfully');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        
        // Re-subscribe to sessions if we were previously subscribed
        if (this.subscribedSessions.size > 0) {
          const sessionIds = Array.from(this.subscribedSessions);
          console.log(`[ObservabilityWS] Re-subscribing to ${sessionIds.length} session(s)`);
          this.subscribe(sessionIds);
        }
        
        // Notify connection status subscribers
        this._notifySubscribers('connected', { status: 'connected' });
      };
      
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const { type, event: eventData } = data;
          
          console.log(`[ObservabilityWS] Received event: ${type}`);
          
          // Notify all subscribers for this event type
          this._notifySubscribers(type, eventData);
        } catch (error) {
          console.error('[ObservabilityWS] Failed to parse message:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log(`[ObservabilityWS] Disconnected (code: ${event.code})`);
        this.isConnecting = false;
        
        // Notify connection status subscribers
        this._notifySubscribers('disconnected', { 
          status: 'disconnected',
          code: event.code
        });
        
        // Reconnect if not intentionally closed
        if (!this.isIntentionallyClosed) {
          this.reconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        console.error('[ObservabilityWS] WebSocket error:', error);
        this.isConnecting = false;
      };
    } catch (error) {
      console.error('[ObservabilityWS] Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.reconnect();
    }
  }
  
  /**
   * Reconnect with exponential backoff.
   */
  reconnect() {
    if (this.isIntentionallyClosed) {
      console.log('[ObservabilityWS] Not reconnecting (intentionally closed)');
      return;
    }
    
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[ObservabilityWS] Max reconnect attempts reached');
      this._notifySubscribers('error', {
        message: 'Failed to reconnect after maximum attempts'
      });
      return;
    }
    
    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);
    
    console.log(`[ObservabilityWS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      if (!this.isIntentionallyClosed) {
        this.connect();
      }
    }, delay);
  }
  
  /**
   * Subscribe to session events.
   * 
   * @param {string|string[]} sessionIds - Session ID(s) to subscribe to
   */
  subscribe(sessionIds) {
    const ids = Array.isArray(sessionIds) ? sessionIds : [sessionIds];
    
    // Remember subscriptions
    ids.forEach(id => this.subscribedSessions.add(id));
    
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = {
        action: 'subscribe',
        session_ids: ids
      };
      
      console.log(`[ObservabilityWS] Subscribing to session(s):`, ids);
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[ObservabilityWS] Cannot subscribe - WebSocket not open');
    }
  }
  
  /**
   * Unsubscribe from session events.
   * 
   * @param {string|string[]} sessionIds - Session ID(s) to unsubscribe from
   */
  unsubscribe(sessionIds) {
    const ids = Array.isArray(sessionIds) ? sessionIds : [sessionIds];
    
    // Remove from remembered subscriptions
    ids.forEach(id => this.subscribedSessions.delete(id));
    
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = {
        action: 'unsubscribe',
        session_ids: ids
      };
      
      console.log(`[ObservabilityWS] Unsubscribing from session(s):`, ids);
      this.ws.send(JSON.stringify(message));
    }
  }
  
  /**
   * Subscribe to event type.
   * 
   * @param {string} eventType - Event type to listen for
   * @param {function} callback - Callback function
   */
  on(eventType, callback) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, []);
    }
    this.subscribers.get(eventType).push(callback);
    
    console.log(`[ObservabilityWS] Added subscriber for event type: ${eventType}`);
  }
  
  /**
   * Unsubscribe from event type.
   * 
   * @param {string} eventType - Event type
   * @param {function} callback - Callback function to remove
   */
  off(eventType, callback) {
    if (this.subscribers.has(eventType)) {
      const callbacks = this.subscribers.get(eventType);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
        console.log(`[ObservabilityWS] Removed subscriber for event type: ${eventType}`);
      }
    }
  }
  
  /**
   * Notify all subscribers for an event type.
   * 
   * @param {string} eventType - Event type
   * @param {object} eventData - Event data
   * @private
   */
  _notifySubscribers(eventType, eventData) {
    if (this.subscribers.has(eventType)) {
      const callbacks = this.subscribers.get(eventType);
      callbacks.forEach(callback => {
        try {
          callback(eventData);
        } catch (error) {
          console.error(`[ObservabilityWS] Error in event callback for ${eventType}:`, error);
        }
      });
    }
  }
  
  /**
   * Disconnect from WebSocket server.
   */
  disconnect() {
    console.log('[ObservabilityWS] Disconnecting...');
    this.isIntentionallyClosed = true;
    this.subscribedSessions.clear();
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
  
  /**
   * Get current connection status.
   * 
   * @returns {string} 'connecting', 'open', 'closing', 'closed'
   */
  getStatus() {
    if (!this.ws) return 'closed';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'open';
      case WebSocket.CLOSING:
        return 'closing';
      case WebSocket.CLOSED:
        return 'closed';
      default:
        return 'unknown';
    }
  }
  
  /**
   * Check if WebSocket is connected.
   * 
   * @returns {boolean}
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

export default ObservabilityWebSocket;


