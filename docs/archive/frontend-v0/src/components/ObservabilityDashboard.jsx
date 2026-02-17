/**
 * Multi-Session Observability Dashboard
 * 
 * Real-time monitoring of all active sessions with automatic updates via WebSocket.
 */

import { useState, useEffect } from 'react';
import useObservability from '../hooks/useObservability';
import SessionDetailView from './SessionDetailView';
import './ObservabilityDashboard.css';

function ObservabilityDashboard() {
  const [sessions, setSessions] = useState([]);
  const [filter, setFilter] = useState('all'); // all, in_progress, blocked, completed
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null); // For viewing session details
  
  const { connected, connecting, subscribe, getEventsBySession } = useObservability();
  
  // Load initial session data
  useEffect(() => {
    loadSessions();
  }, []);
  
  // Subscribe to all sessions for real-time updates
  useEffect(() => {
    if (connected && sessions.length > 0) {
      const sessionIds = sessions.map(s => s.session_id);
      subscribe(sessionIds);
    }
  }, [connected, sessions, subscribe]);
  
  // Handle real-time activity state changes
  useEffect(() => {
    sessions.forEach(session => {
      const events = getEventsBySession(session.session_id);
      const activityChanges = events.filter(e => e.type === 'activity_state_change');
      
      if (activityChanges.length > 0) {
        // Update session based on events
        updateSessionFromEvents(session.session_id, activityChanges);
      }
    });
  }, [sessions, getEventsBySession]);
  
  const loadSessions = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Load sessions from API
      const response = await fetch('/api/v1/sessions');
      if (!response.ok) throw new Error('Failed to load sessions');
      
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  const updateSessionFromEvents = (sessionId, events) => {
    setSessions(prev => prev.map(session => {
      if (session.session_id !== sessionId) return session;
      
      // Count activity status changes
      let completedCount = session.completed_activities || 0;
      let inProgressCount = session.in_progress_activities || 0;
      let blockedCount = session.blocked_activities || 0;
      
      events.forEach(event => {
        const { new_status, old_status } = event.data;
        
        // Adjust counts
        if (old_status === 'in_progress') inProgressCount--;
        if (old_status === 'blocked') blockedCount--;
        
        if (new_status === 'goal_met') completedCount++;
        else if (new_status === 'in_progress') inProgressCount++;
        else if (new_status === 'blocked') blockedCount++;
      });
      
      return {
        ...session,
        completed_activities: completedCount,
        in_progress_activities: inProgressCount,
        blocked_activities: blockedCount,
        progress_percent: Math.round((completedCount / (session.total_activities || 1)) * 100)
      };
    }));
  };
  
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return '🟢';
      case 'in_progress': return '🔵';
      case 'blocked': return '🔴';
      default: return '🟡';
    }
  };
  
  const filteredSessions = sessions.filter(session => {
    if (filter === 'all') return true;
    return session.status === filter;
  });
  
  if (loading) {
    return (
      <div className="observability-dashboard">
        <div className="loading">Loading sessions...</div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="observability-dashboard">
        <div className="error">Error: {error}</div>
        <button onClick={loadSessions}>Retry</button>
      </div>
    );
  }
  
  // If a session is selected, show detail view
  if (selectedSession) {
    return (
      <div className="observability-wrapper">
        <button 
          className="back-button"
          onClick={() => setSelectedSession(null)}
        >
          ← Back to Dashboard
        </button>
        <SessionDetailView sessionId={selectedSession} />
      </div>
    );
  }
  
  return (
    <div className="observability-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <h1>Process Observability Dashboard</h1>
        <div className="connection-status">
          {connecting && <span className="status-connecting">⚡ Connecting...</span>}
          {connected && <span className="status-connected">🟢 Live</span>}
          {!connecting && !connected && <span className="status-disconnected">🔴 Disconnected</span>}
        </div>
      </div>
      
      {/* System Stats */}
      <div className="system-stats">
        <div className="stat-card">
          <div className="stat-value">{sessions.length}</div>
          <div className="stat-label">Active Sessions</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {sessions.reduce((sum, s) => sum + (s.total_activities || 0), 0)}
          </div>
          <div className="stat-label">Total Activities</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {sessions.reduce((sum, s) => sum + (s.compute_instances?.length || 0), 0)}
          </div>
          <div className="stat-label">Compute Resources</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {sessions.reduce((sum, s) => sum + (s.active_agents?.length || 0), 0)}
          </div>
          <div className="stat-label">Active Agents</div>
        </div>
      </div>
      
      {/* Filters */}
      <div className="dashboard-filters">
        <button 
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          All ({sessions.length})
        </button>
        <button 
          className={filter === 'in_progress' ? 'active' : ''}
          onClick={() => setFilter('in_progress')}
        >
          In Progress ({sessions.filter(s => s.status === 'in_progress').length})
        </button>
        <button 
          className={filter === 'blocked' ? 'active' : ''}
          onClick={() => setFilter('blocked')}
        >
          Blocked ({sessions.filter(s => s.blocked_activities > 0).length})
        </button>
        <button 
          className={filter === 'completed' ? 'active' : ''}
          onClick={() => setFilter('completed')}
        >
          Completed ({sessions.filter(s => s.status === 'completed').length})
        </button>
      </div>
      
      {/* Session List */}
      <div className="session-list">
        {filteredSessions.length === 0 ? (
          <div className="empty-state">
            <p>No sessions found</p>
            <button onClick={loadSessions}>Refresh</button>
          </div>
        ) : (
          filteredSessions.map(session => (
            <SessionCard 
              key={session.session_id} 
              session={session}
              onViewDetails={(sessionId) => setSelectedSession(sessionId)}
            />
          ))
        )}
      </div>
      
      {/* Refresh Button */}
      <div className="dashboard-footer">
        <button onClick={loadSessions} className="refresh-button">
          🔄 Refresh
        </button>
      </div>
    </div>
  );
}

function SessionCard({ session, onViewDetails }) {
  const {
    session_id,
    business_goal,
    status,
    total_activities = 0,
    completed_activities = 0,
    in_progress_activities = 0,
    blocked_activities = 0,
    proposed_activities = 0,
    progress_percent = 0,
    duration_seconds = 0,
    map_version = 1,
    compute_instances = [],
    active_agents = [],
    created_at
  } = session;
  
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return '🟢';
      case 'in_progress': return '🔵';
      case 'blocked': return '🔴';
      default: return '🟡';
    }
  };
  
  const formatDuration = (seconds) => {
    if (!seconds) return '0m';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };
  
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleString();
  };
  
  return (
    <div className={`session-card ${blocked_activities > 0 ? 'has-blocker' : ''}`}>
      <div className="session-header">
        <div className="session-title">
          <span className="status-icon">{getStatusIcon(status)}</span>
          <h3>{session_id}</h3>
          <span className="status-badge">{status}</span>
        </div>
      </div>
      
      <div className="session-goal">
        <strong>Goal:</strong> {business_goal || 'No goal specified'}
      </div>
      
      <div className="session-progress">
        <div className="progress-bar-container">
          <div 
            className="progress-bar-fill" 
            style={{ width: `${progress_percent}%` }}
          />
        </div>
        <div className="progress-text">
          {progress_percent}% ({completed_activities}/{total_activities})
        </div>
      </div>
      
      <div className="session-stats">
        <div className="stat-row">
          <div className="stat-item">
            <span className="stat-icon">📋</span>
            <span>Activities:</span>
            <span className="stat-breakdown">
              {completed_activities} 🟢 {in_progress_activities} 🔵 {proposed_activities} 🟡
              {blocked_activities > 0 && <span className="blocker-badge">{blocked_activities} 🔴</span>}
            </span>
          </div>
        </div>
        
        <div className="stat-row">
          <div className="stat-item">
            <span className="stat-icon">⏱️</span>
            <span>Duration: {formatDuration(duration_seconds)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-icon">🔄</span>
            <span>Map v{map_version}</span>
          </div>
        </div>
        
        <div className="stat-row">
          <div className="stat-item">
            <span className="stat-icon">💻</span>
            <span>Compute: {compute_instances.length} instances</span>
          </div>
          <div className="stat-item">
            <span className="stat-icon">🤖</span>
            <span>Agents: {active_agents.length} active</span>
          </div>
        </div>
      </div>
      
      {blocked_activities > 0 && (
        <div className="blocker-alert">
          ⚠️ {blocked_activities} blocked activit{blocked_activities === 1 ? 'y' : 'ies'}
        </div>
      )}
      
      <div className="session-footer">
        <div className="session-meta">
          Created: {formatDate(created_at)}
        </div>
        <div className="session-actions">
          <button 
            className="btn-primary"
            onClick={() => onViewDetails(session_id)}
          >
            View Details
          </button>
        </div>
      </div>
    </div>
  );
}

export default ObservabilityDashboard;


