/**
 * Timeline View
 * 
 * Chronological event stream showing:
 * - Activity state changes
 * - Agent assignments
 * - Exchanges/conversations
 * - Blockers identified
 * - Process map evolution
 * 
 * Real-time updates via WebSocket.
 */

import { useState, useEffect, useRef } from 'react';
import useObservability from '../hooks/useObservability';
import './TimelineView.css';

function TimelineView({ sessionId }) {
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const timelineEndRef = useRef(null);
  
  const { connected, subscribe, getEventsBySession } = useObservability();
  
  // Subscribe to session
  useEffect(() => {
    if (connected && sessionId) {
      subscribe([sessionId]);
    }
  }, [connected, sessionId, subscribe]);
  
  // Get events and update
  useEffect(() => {
    if (!sessionId) return;
    
    const allEvents = getEventsBySession(sessionId);
    setEvents(allEvents);
    
    // Auto-scroll to bottom on new events
    if (autoScroll && timelineEndRef.current) {
      timelineEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [sessionId, getEventsBySession, autoScroll]);
  
  const getEventIcon = (eventType) => {
    const icons = {
      'activity_state_change': '🔄',
      'activity_exchange': '💬',
      'blocker_identified': '⚠️',
      'process_map_evolved': '🔄',
      'agent_assigned': '🤖',
      'resource_utilization': '💻',
      'process_map_grouping': '📁'
    };
    return icons[eventType] || '📌';
  };
  
  const getEventColor = (eventType) => {
    const colors = {
      'activity_state_change': '#3b82f6',
      'activity_exchange': '#8b5cf6',
      'blocker_identified': '#ef4444',
      'process_map_evolved': '#10b981',
      'agent_assigned': '#f59e0b',
      'resource_utilization': '#6b7280',
      'process_map_grouping': '#14b8a6'
    };
    return colors[eventType] || '#6b7280';
  };
  
  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffSeconds = Math.floor((now - date) / 1000);
    
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    
    return date.toLocaleTimeString();
  };
  
  const filteredEvents = events.filter(event => {
    if (filter === 'all') return true;
    return event.type === filter;
  });
  
  const eventTypeOptions = [
    { value: 'all', label: 'All Events', count: events.length },
    { value: 'activity_state_change', label: 'State Changes', count: events.filter(e => e.type === 'activity_state_change').length },
    { value: 'activity_exchange', label: 'Exchanges', count: events.filter(e => e.type === 'activity_exchange').length },
    { value: 'blocker_identified', label: 'Blockers', count: events.filter(e => e.type === 'blocker_identified').length },
    { value: 'agent_assigned', label: 'Agent Assignments', count: events.filter(e => e.type === 'agent_assigned').length },
    { value: 'process_map_evolved', label: 'Map Evolution', count: events.filter(e => e.type === 'process_map_evolved').length }
  ];
  
  return (
    <div className="timeline-view">
      {/* Controls */}
      <div className="timeline-controls">
        <div className="timeline-filters">
          {eventTypeOptions.map(option => (
            <button
              key={option.value}
              className={filter === option.value ? 'active' : ''}
              onClick={() => setFilter(option.value)}
            >
              {option.label} ({option.count})
            </button>
          ))}
        </div>
        
        <div className="timeline-settings">
          <label>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <div className="connection-status">
            {connected ? '🟢 Live' : '🔴 Offline'}
          </div>
        </div>
      </div>
      
      {/* Timeline */}
      <div className="timeline-container">
        {filteredEvents.length === 0 ? (
          <div className="timeline-empty">
            <p>No events yet</p>
            <p className="timeline-empty-hint">
              Events will appear here as the process runs
            </p>
          </div>
        ) : (
          <div className="timeline-events">
            {filteredEvents.map((event, index) => (
              <TimelineEvent
                key={`${event.type}-${event.timestamp}-${index}`}
                event={event}
                icon={getEventIcon(event.type)}
                color={getEventColor(event.type)}
                formatTimestamp={formatTimestamp}
              />
            ))}
            <div ref={timelineEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineEvent({ event, icon, color, formatTimestamp }) {
  const [expanded, setExpanded] = useState(false);
  
  const renderEventContent = () => {
    const { type, data, timestamp } = event;
    
    switch (type) {
      case 'activity_state_change':
        return (
          <div className="event-content">
            <div className="event-title">
              Activity {data.activity_id} changed status
            </div>
            <div className="event-details">
              <span className={`status-badge ${data.old_status}`}>
                {data.old_status}
              </span>
              <span className="arrow">→</span>
              <span className={`status-badge ${data.new_status}`}>
                {data.new_status}
              </span>
            </div>
            {data.agent_id && (
              <div className="event-meta">Agent: {data.agent_id}</div>
            )}
            {data.compute_instance_id && (
              <div className="event-meta">Compute: {data.compute_instance_id}</div>
            )}
          </div>
        );
      
      case 'activity_exchange':
        return (
          <div className="event-content">
            <div className="event-title">
              Exchange in activity {data.activity_id}
            </div>
            <div className="event-details">
              <strong>{data.speaker}:</strong> {data.message.substring(0, 100)}
              {data.message.length > 100 && '...'}
            </div>
            {data.intent && (
              <div className="event-meta">Intent: {data.intent}</div>
            )}
            {expanded && data.message.length > 100 && (
              <div className="event-full-message">
                {data.message}
              </div>
            )}
          </div>
        );
      
      case 'blocker_identified':
        return (
          <div className="event-content">
            <div className="event-title">
              Blocker identified in activity {data.activity_id}
            </div>
            <div className="event-details blocker">
              {data.description}
            </div>
            <div className="event-meta">
              Identified by: {data.identified_by}
            </div>
          </div>
        );
      
      case 'process_map_evolved':
        return (
          <div className="event-content">
            <div className="event-title">
              Process map evolved
            </div>
            <div className="event-details">
              v{data.previous_version} → v{data.new_version}
            </div>
            <div className="event-meta">{data.reasoning}</div>
            {data.triggered_by && (
              <div className="event-meta">Triggered by: {data.triggered_by}</div>
            )}
            {expanded && data.changes && (
              <div className="event-changes">
                <pre>{JSON.stringify(data.changes, null, 2)}</pre>
              </div>
            )}
          </div>
        );
      
      case 'agent_assigned':
        return (
          <div className="event-content">
            <div className="event-title">
              Agent assigned to activity {data.activity_id}
            </div>
            <div className="event-details">
              <strong>{data.agent_name}</strong> ({data.agent_id})
            </div>
            <div className="event-meta">Role: {data.role}</div>
          </div>
        );
      
      case 'resource_utilization':
        return (
          <div className="event-content">
            <div className="event-title">
              Resource utilization update
            </div>
            <div className="event-details">
              <div>CPU: {data.cpu_usage?.toFixed(1)}%</div>
              <div>Memory: {data.memory_usage_gb?.toFixed(2)} GB</div>
            </div>
            <div className="event-meta">
              Active agents: {data.active_agents?.length || 0}
            </div>
          </div>
        );
      
      case 'process_map_grouping':
        return (
          <div className="event-content">
            <div className="event-title">
              Activity group created: {data.group_name}
            </div>
            <div className="event-details">
              {data.activity_ids?.length || 0} activit{(data.activity_ids?.length || 0) !== 1 ? 'ies' : 'y'} grouped
            </div>
            {data.parent_group_id && (
              <div className="event-meta">Parent: {data.parent_group_id}</div>
            )}
          </div>
        );
      
      default:
        return (
          <div className="event-content">
            <div className="event-title">
              Unknown event type: {type}
            </div>
            {expanded && (
              <div className="event-raw">
                <pre>{JSON.stringify(event, null, 2)}</pre>
              </div>
            )}
          </div>
        );
    }
  };
  
  const hasExpandable = 
    (event.type === 'activity_exchange' && event.data.message?.length > 100) ||
    (event.type === 'process_map_evolved' && event.data.changes) ||
    event.type === 'unknown';
  
  return (
    <div className="timeline-event">
      <div className="event-marker" style={{ backgroundColor: color }}>
        {icon}
      </div>
      
      <div className="event-card">
        <div className="event-header">
          <span className="event-timestamp">
            {formatTimestamp(event.timestamp)}
          </span>
          {hasExpandable && (
            <button
              className="event-expand"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '▼' : '▶'}
            </button>
          )}
        </div>
        
        {renderEventContent()}
      </div>
    </div>
  );
}

export default TimelineView;


