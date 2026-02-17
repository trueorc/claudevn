/**
 * Workflow Graph Visualization
 * 
 * Displays process activities as a workflow graph with:
 * - Activity nodes grouped by semantic grouping
 * - Dependency arrows
 * - Collapsible groups (e.g., completed phases)
 * - Real-time status updates
 */

import { useState, useEffect, useRef } from 'react';
import './WorkflowView.css';

function WorkflowView({ processMap, sessionId }) {
  const [collapsedGroups, setCollapsedGroups] = useState(new Set());
  const [selectedActivity, setSelectedActivity] = useState(null);
  const [layoutMode, setLayoutMode] = useState('groups'); // 'groups' or 'flat'
  const graphRef = useRef(null);
  
  if (!processMap) {
    return <div className="workflow-view-empty">No process map available</div>;
  }
  
  const activities = processMap.activities || {};
  const activityGroups = processMap.activity_groups || {};
  const groupOrder = processMap.group_order || [];
  
  // Auto-collapse completed groups
  useEffect(() => {
    const completedGroupIds = Object.keys(activityGroups).filter(groupId => {
      const group = activityGroups[groupId];
      return group.status === 'completed';
    });
    
    setCollapsedGroups(new Set(completedGroupIds));
  }, [activityGroups]);
  
  const toggleGroup = (groupId) => {
    setCollapsedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupId)) {
        newSet.delete(groupId);
      } else {
        newSet.add(groupId);
      }
      return newSet;
    });
  };
  
  const getStatusColor = (status) => {
    const colors = {
      'proposed': '#f59e0b',
      'in_progress': '#3b82f6',
      'goal_met': '#10b981',
      'blocked': '#ef4444',
      'revisit': '#8b5cf6'
    };
    return colors[status] || '#6b7280';
  };
  
  const getStatusLabel = (status) => {
    const labels = {
      'proposed': 'Proposed',
      'in_progress': 'In Progress',
      'goal_met': 'Completed',
      'blocked': 'Blocked',
      'revisit': 'Revisit'
    };
    return labels[status] || status;
  };
  
  const renderActivityNode = (activity, activityId) => {
    const isSelected = selectedActivity === activityId;
    const hasBlockers = activity.blockers && activity.blockers.length > 0;
    
    return (
      <div
        key={activityId}
        className={`activity-node ${activity.status} ${isSelected ? 'selected' : ''} ${hasBlockers ? 'has-blockers' : ''}`}
        onClick={() => setSelectedActivity(activityId)}
      >
        <div className="activity-header">
          <span 
            className="activity-status-indicator"
            style={{ backgroundColor: getStatusColor(activity.status) }}
          />
          <span className="activity-id">{activityId}</span>
        </div>
        
        <div className="activity-goal">
          {activity.goal}
        </div>
        
        <div className="activity-meta">
          {activity.assigned_agents && activity.assigned_agents.length > 0 && (
            <div className="activity-agents">
              🤖 {activity.assigned_agents.length} agent{activity.assigned_agents.length !== 1 ? 's' : ''}
            </div>
          )}
          
          {hasBlockers && (
            <div className="activity-blockers">
              ⚠️ {activity.blockers.length} blocker{activity.blockers.length !== 1 ? 's' : ''}
            </div>
          )}
          
          {activity.depends_on && activity.depends_on.length > 0 && (
            <div className="activity-dependencies">
              ↓ {activity.depends_on.length} dep{activity.depends_on.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
        
        <div className="activity-status-label">
          {getStatusLabel(activity.status)}
        </div>
      </div>
    );
  };
  
  const renderGroup = (groupId) => {
    const group = activityGroups[groupId];
    if (!group) return null;
    
    const isCollapsed = collapsedGroups.has(groupId);
    const groupActivities = (group.activity_ids || [])
      .map(id => ({ id, activity: activities[id] }))
      .filter(item => item.activity);
    
    const completedCount = groupActivities.filter(
      item => item.activity.status === 'goal_met'
    ).length;
    
    const totalCount = groupActivities.length;
    const progressPercent = totalCount > 0 
      ? Math.round((completedCount / totalCount) * 100)
      : 0;
    
    return (
      <div key={groupId} className={`activity-group ${isCollapsed ? 'collapsed' : ''}`}>
        <div className="group-header" onClick={() => toggleGroup(groupId)}>
          <span className="group-toggle">
            {isCollapsed ? '▶' : '▼'}
          </span>
          <div className="group-info">
            <h3>{group.name}</h3>
            <div className="group-stats">
              <span>{completedCount}/{totalCount} completed</span>
              <span>•</span>
              <span>{progressPercent}%</span>
              {group.status && <span className={`group-status ${group.status}`}>{group.status}</span>}
            </div>
          </div>
        </div>
        
        {isCollapsed ? (
          <div className="group-collapsed-summary">
            <div className="collapsed-progress">
              <div 
                className="collapsed-progress-bar"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        ) : (
          <div className="group-activities">
            {groupActivities.map(({ id, activity }) =>
              renderActivityNode(activity, id)
            )}
          </div>
        )}
      </div>
    );
  };
  
  const renderUngroupedActivities = () => {
    const groupedActivityIds = new Set(
      Object.values(activityGroups).flatMap(g => g.activity_ids || [])
    );
    
    const ungrouped = Object.entries(activities)
      .filter(([id]) => !groupedActivityIds.has(id));
    
    if (ungrouped.length === 0) return null;
    
    return (
      <div className="activity-group ungrouped">
        <div className="group-header">
          <h3>Other Activities</h3>
          <div className="group-stats">
            <span>{ungrouped.length} activit{ungrouped.length !== 1 ? 'ies' : 'y'}</span>
          </div>
        </div>
        <div className="group-activities">
          {ungrouped.map(([id, activity]) =>
            renderActivityNode(activity, id)
          )}
        </div>
      </div>
    );
  };
  
  return (
    <div className="workflow-view">
      {/* Controls */}
      <div className="workflow-controls">
        <div className="view-mode-toggle">
          <button
            className={layoutMode === 'groups' ? 'active' : ''}
            onClick={() => setLayoutMode('groups')}
          >
            Grouped View
          </button>
          <button
            className={layoutMode === 'flat' ? 'active' : ''}
            onClick={() => setLayoutMode('flat')}
          >
            Flat View
          </button>
        </div>
        
        <div className="workflow-actions">
          <button onClick={() => setCollapsedGroups(new Set())}>
            Expand All
          </button>
          <button onClick={() => setCollapsedGroups(new Set(Object.keys(activityGroups)))}>
            Collapse All
          </button>
        </div>
      </div>
      
      {/* Legend */}
      <div className="workflow-legend">
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#f59e0b' }} />
          <span>Proposed</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#3b82f6' }} />
          <span>In Progress</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#10b981' }} />
          <span>Completed</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#ef4444' }} />
          <span>Blocked</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#8b5cf6' }} />
          <span>Revisit</span>
        </div>
      </div>
      
      {/* Workflow Graph */}
      <div className="workflow-graph" ref={graphRef}>
        {layoutMode === 'groups' ? (
          <>
            {groupOrder.map(groupId => renderGroup(groupId))}
            {renderUngroupedActivities()}
          </>
        ) : (
          <div className="activity-group">
            <div className="group-activities flat">
              {Object.entries(activities).map(([id, activity]) =>
                renderActivityNode(activity, id)
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* Activity Detail Panel */}
      {selectedActivity && activities[selectedActivity] && (
        <ActivityDetailPanel
          activity={activities[selectedActivity]}
          activityId={selectedActivity}
          onClose={() => setSelectedActivity(null)}
        />
      )}
    </div>
  );
}

function ActivityDetailPanel({ activity, activityId, onClose }) {
  return (
    <div className="activity-detail-panel">
      <div className="panel-header">
        <h3>Activity Details</h3>
        <button onClick={onClose} className="close-button">✕</button>
      </div>
      
      <div className="panel-content">
        <div className="detail-section">
          <label>Activity ID</label>
          <div className="detail-value">{activityId}</div>
        </div>
        
        <div className="detail-section">
          <label>Goal</label>
          <div className="detail-value">{activity.goal}</div>
        </div>
        
        <div className="detail-section">
          <label>Status</label>
          <div className="detail-value">
            <span className={`status-badge ${activity.status}`}>
              {activity.status}
            </span>
          </div>
        </div>
        
        {activity.assigned_agents && activity.assigned_agents.length > 0 && (
          <div className="detail-section">
            <label>Assigned Agents</label>
            <div className="detail-value">
              <ul>
                {activity.assigned_agents.map((agent, idx) => (
                  <li key={idx}>
                    {agent.agent_id} ({agent.role})
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        
        {activity.depends_on && activity.depends_on.length > 0 && (
          <div className="detail-section">
            <label>Dependencies</label>
            <div className="detail-value">
              <ul>
                {activity.depends_on.map((depId, idx) => (
                  <li key={idx}>{depId}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        
        {activity.blockers && activity.blockers.length > 0 && (
          <div className="detail-section">
            <label>Blockers</label>
            <div className="detail-value blockers">
              {activity.blockers.map((blocker, idx) => (
                <div key={idx} className="blocker-item">
                  <div className="blocker-desc">{blocker.description}</div>
                  <div className="blocker-meta">
                    Identified by: {blocker.identified_by}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {activity.key_findings && activity.key_findings.length > 0 && (
          <div className="detail-section">
            <label>Key Findings</label>
            <div className="detail-value">
              <ul>
                {activity.key_findings.map((finding, idx) => (
                  <li key={idx}>{finding}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        
        <div className="detail-section">
          <label>Timeline</label>
          <div className="detail-value timeline">
            {activity.proposed_at && (
              <div>Proposed: {new Date(activity.proposed_at).toLocaleString()}</div>
            )}
            {activity.started_at && (
              <div>Started: {new Date(activity.started_at).toLocaleString()}</div>
            )}
            {activity.completed_at && (
              <div>Completed: {new Date(activity.completed_at).toLocaleString()}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default WorkflowView;


