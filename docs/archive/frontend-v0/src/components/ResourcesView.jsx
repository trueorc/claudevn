/**
 * Resources View
 * 
 * Displays compute resources and agent utilization:
 * - Compute instances status
 * - CPU and memory usage
 * - Active agents per instance
 * - Real-time resource utilization updates
 */

import { useState, useEffect } from 'react';
import useObservability from '../hooks/useObservability';
import './ResourcesView.css';

function ResourcesView({ sessionId, processMap }) {
  const [computeInstances, setComputeInstances] = useState([]);
  const [resourceMetrics, setResourceMetrics] = useState({});
  const [loading, setLoading] = useState(true);
  
  const { connected, subscribe, getEventsBySession } = useObservability();
  
  // Subscribe to session for real-time updates
  useEffect(() => {
    if (connected && sessionId) {
      subscribe([sessionId]);
    }
  }, [connected, sessionId, subscribe]);
  
  // Load compute instances
  useEffect(() => {
    if (sessionId) {
      loadComputeInstances();
    }
  }, [sessionId]);
  
  // Handle resource utilization events
  useEffect(() => {
    if (!sessionId) return;
    
    const events = getEventsBySession(sessionId);
    const resourceEvents = events.filter(e => e.type === 'resource_utilization');
    
    resourceEvents.forEach(event => {
      const { compute_instance_id, cpu_usage, memory_usage_gb, active_agents, timestamp } = event.data;
      
      setResourceMetrics(prev => ({
        ...prev,
        [compute_instance_id]: {
          cpu_usage,
          memory_usage_gb,
          active_agents,
          last_update: timestamp
        }
      }));
    });
  }, [sessionId, getEventsBySession]);
  
  const loadComputeInstances = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/compute/instances');
      if (!response.ok) throw new Error('Failed to load compute instances');
      
      const data = await response.json();
      setComputeInstances(data.instances || []);
    } catch (err) {
      console.error('Error loading compute instances:', err);
    } finally {
      setLoading(false);
    }
  };
  
  const getActiveAgents = () => {
    if (!processMap || !processMap.activities) return [];
    
    const agents = new Set();
    Object.values(processMap.activities).forEach(activity => {
      if (activity.status === 'in_progress' && activity.assigned_agents) {
        activity.assigned_agents.forEach(agent => {
          agents.add(JSON.stringify({
            agent_id: agent.agent_id,
            role: agent.role,
            activity_id: activity.activity_id
          }));
        });
      }
    });
    
    return Array.from(agents).map(a => JSON.parse(a));
  };
  
  const activeAgents = getActiveAgents();
  
  if (loading) {
    return (
      <div className="resources-view">
        <div className="loading">Loading resources...</div>
      </div>
    );
  }
  
  return (
    <div className="resources-view">
      {/* Summary Stats */}
      <div className="resources-summary">
        <div className="summary-card">
          <div className="summary-icon">💻</div>
          <div className="summary-info">
            <div className="summary-value">{computeInstances.length}</div>
            <div className="summary-label">Compute Instances</div>
          </div>
        </div>
        
        <div className="summary-card">
          <div className="summary-icon">🤖</div>
          <div className="summary-info">
            <div className="summary-value">{activeAgents.length}</div>
            <div className="summary-label">Active Agents</div>
          </div>
        </div>
        
        <div className="summary-card">
          <div className="summary-icon">
            {connected ? '🟢' : '🔴'}
          </div>
          <div className="summary-info">
            <div className="summary-value">{connected ? 'Live' : 'Offline'}</div>
            <div className="summary-label">Connection</div>
          </div>
        </div>
      </div>
      
      {/* Compute Instances */}
      <div className="section">
        <h2>💻 Compute Instances</h2>
        <div className="compute-instances-grid">
          {computeInstances.length === 0 ? (
            <div className="empty-state">No compute instances available</div>
          ) : (
            computeInstances.map(instance => (
              <ComputeInstanceCard
                key={instance.instance_id}
                instance={instance}
                metrics={resourceMetrics[instance.instance_id]}
              />
            ))
          )}
        </div>
      </div>
      
      {/* Active Agents */}
      <div className="section">
        <h2>🤖 Active Agents</h2>
        <div className="active-agents-list">
          {activeAgents.length === 0 ? (
            <div className="empty-state">No agents currently active</div>
          ) : (
            activeAgents.map((agent, idx) => (
              <AgentCard key={idx} agent={agent} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function ComputeInstanceCard({ instance, metrics }) {
  const {
    instance_id,
    name,
    status,
    capabilities = {},
    registered_at
  } = instance;
  
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp).toLocaleString();
  };
  
  const getStatusColor = (status) => {
    const colors = {
      'active': '#10b981',
      'inactive': '#6b7280',
      'busy': '#f59e0b',
      'error': '#ef4444'
    };
    return colors[status] || '#6b7280';
  };
  
  return (
    <div className="compute-instance-card">
      <div className="instance-header">
        <div className="instance-title">
          <span 
            className="instance-status"
            style={{ backgroundColor: getStatusColor(status) }}
          />
          <h3>{name || instance_id}</h3>
        </div>
        <span className={`status-badge ${status}`}>{status}</span>
      </div>
      
      <div className="instance-id">
        ID: <code>{instance_id}</code>
      </div>
      
      {/* Resource Metrics */}
      {metrics && (
        <div className="instance-metrics">
          <div className="metric">
            <label>CPU Usage</label>
            <div className="metric-bar-container">
              <div 
                className="metric-bar cpu"
                style={{ width: `${metrics.cpu_usage}%` }}
              />
            </div>
            <span className="metric-value">{metrics.cpu_usage?.toFixed(1)}%</span>
          </div>
          
          <div className="metric">
            <label>Memory Usage</label>
            <div className="metric-bar-container">
              <div 
                className="metric-bar memory"
                style={{ width: `${(metrics.memory_usage_gb / 16) * 100}%` }}
              />
            </div>
            <span className="metric-value">{metrics.memory_usage_gb?.toFixed(2)} GB</span>
          </div>
          
          <div className="metric-info">
            <span>🤖 {metrics.active_agents?.length || 0} active agents</span>
            <span className="metric-time">
              Updated {new Date(metrics.last_update).toLocaleTimeString()}
            </span>
          </div>
        </div>
      )}
      
      {/* Capabilities */}
      {capabilities.supported_models && capabilities.supported_models.length > 0 && (
        <div className="instance-capabilities">
          <label>Supported Models</label>
          <div className="capability-tags">
            {capabilities.supported_models.slice(0, 3).map((model, idx) => (
              <span key={idx} className="capability-tag">{model}</span>
            ))}
            {capabilities.supported_models.length > 3 && (
              <span className="capability-tag">+{capabilities.supported_models.length - 3} more</span>
            )}
          </div>
        </div>
      )}
      
      <div className="instance-footer">
        <span className="instance-registered">
          Registered: {formatTimestamp(registered_at)}
        </span>
      </div>
    </div>
  );
}

function AgentCard({ agent }) {
  return (
    <div className="agent-card">
      <div className="agent-icon">🤖</div>
      <div className="agent-info">
        <div className="agent-name">{agent.agent_id}</div>
        <div className="agent-meta">
          <span className="agent-role">{agent.role}</span>
          <span>•</span>
          <span>Activity: {agent.activity_id}</span>
        </div>
      </div>
      <div className="agent-status">
        <span className="status-indicator active">Active</span>
      </div>
    </div>
  );
}

export default ResourcesView;


