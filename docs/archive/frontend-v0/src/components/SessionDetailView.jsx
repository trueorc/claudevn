/**
 * Session Detail View with Tabs
 * 
 * Comprehensive view of a single session with:
 * - Overview: Summary stats and progress
 * - Workflow: Graph visualization with collapsible groups
 * - Timeline: Chronological event stream
 * - Resources: Compute and agent utilization
 */

import { useState, useEffect } from 'react';
import useObservability from '../hooks/useObservability';
import WorkflowView from './WorkflowView';
import TimelineView from './TimelineView';
import ResourcesView from './ResourcesView';
import './SessionDetailView.css';

function SessionDetailView({ sessionId }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [session, setSession] = useState(null);
  const [processMap, setProcessMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const { connected, subscribe, getEventsBySession } = useObservability();
  
  // Load session data
  useEffect(() => {
    if (sessionId) {
      loadSession();
      loadProcessMap();
    }
  }, [sessionId]);
  
  // Subscribe to this session for real-time updates
  useEffect(() => {
    if (connected && sessionId) {
      subscribe([sessionId]);
    }
  }, [connected, sessionId, subscribe]);
  
  // Handle real-time updates
  useEffect(() => {
    if (!sessionId) return;
    
    const events = getEventsBySession(sessionId);
    if (events.length > 0) {
      updateFromEvents(events);
    }
  }, [sessionId, getEventsBySession]);
  
  const loadSession = async () => {
    try {
      const response = await fetch(`/api/v1/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session');
      
      const data = await response.json();
      setSession(data);
    } catch (err) {
      setError(err.message);
    }
  };
  
  const loadProcessMap = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/process-maps/sessions/${sessionId}/map`);
      if (!response.ok) throw new Error('Failed to load process map');
      
      const data = await response.json();
      setProcessMap(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  const updateFromEvents = (events) => {
    // Update process map and session based on events
    events.forEach(event => {
      if (event.type === 'activity_state_change') {
        updateActivityStatus(event.data);
      } else if (event.type === 'process_map_reevaluation') {
        loadProcessMap(); // Reload on reevaluation
      } else if (event.type === 'activity_grouping') {
        updateActivityGroups(event.data);
      }
    });
  };
  
  const updateActivityStatus = (eventData) => {
    const { activity_id, new_status } = eventData;
    
    setProcessMap(prev => {
      if (!prev) return prev;
      
      const activity = prev.activities[activity_id];
      if (activity) {
        activity.status = new_status;
      }
      
      return { ...prev };
    });
  };
  
  const updateActivityGroups = (eventData) => {
    const { group } = eventData;
    
    setProcessMap(prev => {
      if (!prev) return prev;
      
      if (!prev.activity_groups) {
        prev.activity_groups = {};
        prev.group_order = [];
      }
      
      prev.activity_groups[group.group_id] = group;
      if (!prev.group_order.includes(group.group_id)) {
        prev.group_order.push(group.group_id);
      }
      
      return { ...prev };
    });
  };
  
  if (loading && !processMap) {
    return (
      <div className="session-detail-view">
        <div className="loading">Loading session...</div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="session-detail-view">
        <div className="error">Error: {error}</div>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }
  
  if (!processMap) {
    return (
      <div className="session-detail-view">
        <div className="error">Process map not found for session {sessionId}</div>
        <Link to="/observability">← Back to Dashboard</Link>
      </div>
    );
  }
  
  return (
    <div className="session-detail-view">
      {/* Header */}
      <div className="session-header">
        <div className="breadcrumb">
          <Link to="/observability">← Dashboard</Link>
          <span>/</span>
          <span>{sessionId}</span>
        </div>
        
        <div className="session-title-section">
          <h1>{processMap.business_goal}</h1>
          <div className="connection-badge">
            {connected ? '🟢 Live' : '🔴 Offline'}
          </div>
        </div>
        
        <div className="session-meta">
          <span>Session ID: {sessionId}</span>
          <span>•</span>
          <span>Status: {processMap.status}</span>
          <span>•</span>
          <span>Map Version: {processMap.map_version}</span>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="session-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'workflow' ? 'active' : ''}
          onClick={() => setActiveTab('workflow')}
        >
          Workflow
        </button>
        <button
          className={activeTab === 'timeline' ? 'active' : ''}
          onClick={() => setActiveTab('timeline')}
        >
          Timeline
        </button>
        <button
          className={activeTab === 'resources' ? 'active' : ''}
          onClick={() => setActiveTab('resources')}
        >
          Resources
        </button>
      </div>
      
      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <OverviewTab processMap={processMap} session={session} />
        )}
        {activeTab === 'workflow' && (
          <WorkflowView processMap={processMap} sessionId={sessionId} />
        )}
        {activeTab === 'timeline' && (
          <TimelineView sessionId={sessionId} />
        )}
        {activeTab === 'resources' && (
          <ResourcesView sessionId={sessionId} processMap={processMap} />
        )}
      </div>
    </div>
  );
}

function OverviewTab({ processMap, session }) {
  const progress = processMap.get_progress ? processMap.get_progress() : {
    total_activities: Object.keys(processMap.activities || {}).length,
    completed: processMap.completed_activities?.length || 0,
    in_progress: processMap.in_progress_activities?.length || 0,
    blocked: processMap.blocked_activities?.length || 0,
    proposed: processMap.proposed_activities?.length || 0,
    progress_percent: 0
  };
  
  progress.progress_percent = progress.total_activities > 0
    ? Math.round((progress.completed / progress.total_activities) * 100)
    : 0;
  
  return (
    <div className="overview-tab">
      {/* Progress Summary */}
      <div className="section">
        <h2>📊 Progress Summary</h2>
        <div className="progress-card">
          <div className="progress-bar-large">
            <div 
              className="progress-fill"
              style={{ width: `${progress.progress_percent}%` }}
            />
          </div>
          <div className="progress-stats">
            <span>{progress.progress_percent}% Complete</span>
            <span>•</span>
            <span>{progress.completed}/{progress.total_activities} Activities</span>
          </div>
        </div>
      </div>
      
      {/* Activity Status */}
      <div className="section">
        <h2>🎯 Activity Status</h2>
        <div className="status-grid">
          <div className="status-card completed">
            <div className="status-icon">🟢</div>
            <div className="status-count">{progress.completed}</div>
            <div className="status-label">Completed</div>
          </div>
          <div className="status-card in-progress">
            <div className="status-icon">🔵</div>
            <div className="status-count">{progress.in_progress}</div>
            <div className="status-label">In Progress</div>
          </div>
          <div className="status-card proposed">
            <div className="status-icon">🟡</div>
            <div className="status-count">{progress.proposed}</div>
            <div className="status-label">Proposed</div>
          </div>
          <div className="status-card blocked">
            <div className="status-icon">🔴</div>
            <div className="status-count">{progress.blocked}</div>
            <div className="status-label">Blocked</div>
          </div>
        </div>
      </div>
      
      {/* Map Evolution */}
      <div className="section">
        <h2>🔄 Process Map Evolution</h2>
        <div className="evolution-stats">
          <div className="evolution-stat">
            <span className="label">Current Version:</span>
            <span className="value">v{processMap.map_version}</span>
          </div>
          <div className="evolution-stat">
            <span className="label">Reevaluations:</span>
            <span className="value">{processMap.reevaluations?.length || 0}</span>
          </div>
          <div className="evolution-stat">
            <span className="label">Activity Groups:</span>
            <span className="value">{processMap.group_order?.length || 0}</span>
          </div>
        </div>
      </div>
      
      {/* Recent Activity */}
      <div className="section">
        <h2>📝 Recent Activity</h2>
        <div className="recent-activities">
          {processMap.in_progress_activities?.slice(0, 5).map(activityId => {
            const activity = processMap.activities[activityId];
            return activity ? (
              <div key={activityId} className="activity-item">
                <span className="activity-status">🔵</span>
                <span className="activity-goal">{activity.goal}</span>
                <span className="activity-meta">In Progress</span>
              </div>
            ) : null;
          })}
          {(!processMap.in_progress_activities || processMap.in_progress_activities.length === 0) && (
            <div className="empty-state">No activities in progress</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SessionDetailView;


