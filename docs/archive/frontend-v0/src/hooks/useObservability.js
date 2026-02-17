/**
 * React hook for observability WebSocket connection.
 * 
 * Provides easy access to real-time observability events in React components.
 * 
 * @example
 * const { connected, events, subscribe } = useObservability();
 * 
 * useEffect(() => {
 *   subscribe(['session-123']);
 * }, []);
 * 
 * // Listen for specific event types
 * const activityChanges = events.filter(e => e.type === 'activity_state_change');
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import ObservabilityWebSocket from '../services/observabilityWebSocket';

/**
 * Hook for observability WebSocket connection.
 * 
 * @param {object} options - Configuration options
 * @param {string} options.url - WebSocket URL (defaults to localhost:8002)
 * @param {boolean} options.autoConnect - Auto-connect on mount (default: true)
 * @returns {object} Observability state and methods
 */
function useObservability(options = {}) {
  const {
    url = 'ws://localhost:8002/api/v1/observability/stream',
    autoConnect = true
  } = options;
  
  // WebSocket instance (persists across renders)
  const wsRef = useRef(null);
  
  // Connection state
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  
  // Events received
  const [events, setEvents] = useState([]);
  const [latestEvent, setLatestEvent] = useState(null);
  
  // Event counts by type
  const [eventCounts, setEventCounts] = useState({});
  
  /**
   * Initialize WebSocket connection.
   */
  const connect = useCallback(() => {
    if (!wsRef.current) {
      wsRef.current = new ObservabilityWebSocket(url);
      
      // Listen for connection events
      wsRef.current.on('connected', () => {
        console.log('[useObservability] Connected');
        setConnected(true);
        setConnecting(false);
      });
      
      wsRef.current.on('disconnected', () => {
        console.log('[useObservability] Disconnected');
        setConnected(false);
        setConnecting(false);
      });
      
      // Listen for all event types
      const eventTypes = [
        'activity_state_change',
        'exchange',
        'process_map_reevaluation',
        'blocker_identified',
        'activity_grouping',
        'session_created',
        'session_completed'
      ];
      
      eventTypes.forEach(eventType => {
        wsRef.current.on(eventType, (eventData) => {
          const event = {
            type: eventType,
            data: eventData,
            timestamp: new Date().toISOString()
          };
          
          // Add to events array
          setEvents(prev => [...prev, event]);
          setLatestEvent(event);
          
          // Update counts
          setEventCounts(prev => ({
            ...prev,
            [eventType]: (prev[eventType] || 0) + 1
          }));
        });
      });
    }
    
    setConnecting(true);
    wsRef.current.connect();
  }, [url]);
  
  /**
   * Disconnect from WebSocket.
   */
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.disconnect();
      setConnected(false);
      setConnecting(false);
    }
  }, []);
  
  /**
   * Subscribe to session(s).
   * 
   * @param {string|string[]} sessionIds - Session ID(s) to subscribe to
   */
  const subscribe = useCallback((sessionIds) => {
    if (wsRef.current) {
      wsRef.current.subscribe(sessionIds);
    } else {
      console.warn('[useObservability] Cannot subscribe - not connected');
    }
  }, []);
  
  /**
   * Unsubscribe from session(s).
   * 
   * @param {string|string[]} sessionIds - Session ID(s) to unsubscribe from
   */
  const unsubscribe = useCallback((sessionIds) => {
    if (wsRef.current) {
      wsRef.current.unsubscribe(sessionIds);
    }
  }, []);
  
  /**
   * Clear events array.
   */
  const clearEvents = useCallback(() => {
    setEvents([]);
    setLatestEvent(null);
    setEventCounts({});
  }, []);
  
  /**
   * Get events by type.
   * 
   * @param {string} eventType - Event type to filter
   * @returns {array} Events of specified type
   */
  const getEventsByType = useCallback((eventType) => {
    return events.filter(e => e.type === eventType);
  }, [events]);
  
  /**
   * Get events by session.
   * 
   * @param {string} sessionId - Session ID to filter
   * @returns {array} Events for specified session
   */
  const getEventsBySession = useCallback((sessionId) => {
    return events.filter(e => e.data && e.data.session_id === sessionId);
  }, [events]);
  
  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
      }
    };
  }, [autoConnect, connect]);
  
  return {
    // Connection state
    connected,
    connecting,
    
    // Events
    events,
    latestEvent,
    eventCounts,
    
    // Methods
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearEvents,
    getEventsByType,
    getEventsBySession,
    
    // WebSocket instance (for advanced usage)
    ws: wsRef.current
  };
}

export default useObservability;


