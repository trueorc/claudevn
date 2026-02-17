import { useState, useEffect } from 'react';
import { getComputeInstances, deregisterComputeInstance } from '../api';
import LogsModal from './LogsModal';
import './ComputeRegistry.css';

function ComputeRegistry() {
  const [instances, setInstances] = useState([]);
  const [selectedInstance, setSelectedInstance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [showLogsModal, setShowLogsModal] = useState(false);

  useEffect(() => {
    loadInstances();
    
    // Auto-refresh every 5 seconds
    const interval = setInterval(loadInstances, 5000);
    return () => clearInterval(interval);
  }, [statusFilter]);

  const loadInstances = async () => {
    try {
      const filterStatus = statusFilter === 'all' ? null : statusFilter;
      const data = await getComputeInstances(filterStatus);
      setInstances(data.instances || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeregister = async (instanceId) => {
    if (!confirm(`Are you sure you want to deregister ${instanceId}?`)) {
      return;
    }

    try {
      await deregisterComputeInstance(instanceId);
      await loadInstances();
      if (selectedInstance?.instance_id === instanceId) {
        setSelectedInstance(null);
      }
    } catch (err) {
      alert(`Failed to deregister: ${err.message}`);
    }
  };

  const getHeartbeatAge = (lastHeartbeat) => {
    const age = Math.floor((Date.now() - new Date(lastHeartbeat)) / 1000);
    if (age < 60) return `${age}s ago`;
    if (age < 3600) return `${Math.floor(age / 60)}m ago`;
    return `${Math.floor(age / 3600)}h ago`;
  };

  if (loading) {
    return <div className="compute-registry loading">Loading instances...</div>;
  }

  if (error) {
    return (
      <div className="compute-registry error">
        <h2>Error Loading Instances</h2>
        <p>{error}</p>
        <button onClick={loadInstances}>Retry</button>
      </div>
    );
  }

  return (
    <div className="compute-registry">
      <div className="registry-header">
        <h1>Compute Instance Registry</h1>
        <div className="filters">
          <label>Status Filter:</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All Status</option>
            <option value="online">Online Only</option>
            <option value="offline">Offline Only</option>
            <option value="degraded">Degraded Only</option>
          </select>
        </div>
      </div>

      {instances.length === 0 ? (
        <div className="empty-state">
          <h2>No Compute Instances</h2>
          <p>No compute instances registered yet.</p>
          <p>Compute instances will register automatically when they start.</p>
        </div>
      ) : (
        <div className="registry-content">
          <div className="instances-list">
            {instances.map((instance) => (
              <div
                key={instance.instance_id}
                className={`instance-card ${instance.status} ${selectedInstance?.instance_id === instance.instance_id ? 'selected' : ''}`}
                onClick={() => setSelectedInstance(instance)}
              >
                <div className="instance-header">
                  <h3>{instance.name}</h3>
                  <span className={`status-indicator ${instance.status}`}></span>
                </div>
                <div className="instance-id">{instance.instance_id}</div>
                <div className="instance-meta">
                  <span>{instance.capabilities?.agents?.length || 0} agents</span>
                  <span>{instance.capabilities?.tools?.length || 0} tools</span>
                  <span className="heartbeat">{getHeartbeatAge(instance.last_heartbeat)}</span>
                </div>
              </div>
            ))}
          </div>

          {selectedInstance && (
            <div className="instance-details">
              <div className="details-header">
                <h2>{selectedInstance.name}</h2>
                <div className="details-actions">
                  <button
                    className="view-logs-btn"
                    onClick={() => setShowLogsModal(true)}
                  >
                    📋 View Logs
                  </button>
                  <button
                    className="deregister-btn"
                    onClick={() => handleDeregister(selectedInstance.instance_id)}
                  >
                    Deregister
                  </button>
                </div>
              </div>

              <div className="details-section">
                <h3>Instance Information</h3>
                <div className="details-grid">
                  <div className="detail-item">
                    <label>Instance ID:</label>
                    <span className="mono">{selectedInstance.instance_id}</span>
                  </div>
                  <div className="detail-item">
                    <label>Status:</label>
                    <span className={`status-badge ${selectedInstance.status}`}>
                      {selectedInstance.status}
                    </span>
                  </div>
                  <div className="detail-item">
                    <label>Endpoint:</label>
                    <span className="mono">{selectedInstance.endpoint}</span>
                  </div>
                  <div className="detail-item">
                    <label>Version:</label>
                    <span>{selectedInstance.version}</span>
                  </div>
                  <div className="detail-item">
                    <label>Registered:</label>
                    <span>{new Date(selectedInstance.registered_at).toLocaleString()}</span>
                  </div>
                  <div className="detail-item">
                    <label>Last Heartbeat:</label>
                    <span>{new Date(selectedInstance.last_heartbeat).toLocaleString()}</span>
                  </div>
                  <div className="detail-item">
                    <label>Failed Checks:</label>
                    <span>{selectedInstance.failed_health_checks}</span>
                  </div>
                  <div className="detail-item">
                    <label>Heartbeat Interval:</label>
                    <span>{selectedInstance.heartbeat_interval}s</span>
                  </div>
                </div>
              </div>

              <div className="details-section">
                <h3>Capabilities</h3>
                <div className="capabilities">
                  <div className="capability-group">
                    <h4>Agents ({selectedInstance.capabilities?.agents?.length || 0})</h4>
                    {selectedInstance.capabilities?.agents?.length > 0 ? (
                      <ul className="capability-list">
                        {selectedInstance.capabilities.agents.map((agent) => (
                          <li key={agent} className="mono">{agent}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="empty">No agents</p>
                    )}
                  </div>

                  <div className="capability-group">
                    <h4>Tools ({selectedInstance.capabilities?.tools?.length || 0})</h4>
                    {selectedInstance.capabilities?.tools?.length > 0 ? (
                      <ul className="capability-list">
                        {selectedInstance.capabilities.tools.map((tool) => (
                          <li key={tool} className="mono">{tool}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="empty">No tools</p>
                    )}
                  </div>

                  {selectedInstance.capabilities?.resources && (
                    <div className="capability-group">
                      <h4>Resources</h4>
                      <div className="resource-list">
                        {selectedInstance.capabilities.resources.cpu_count && (
                          <div className="resource-item">
                            <span>CPU:</span>
                            <span>{selectedInstance.capabilities.resources.cpu_count} cores</span>
                          </div>
                        )}
                        {selectedInstance.capabilities.resources.memory_gb && (
                          <div className="resource-item">
                            <span>Memory:</span>
                            <span>{selectedInstance.capabilities.resources.memory_gb} GB</span>
                          </div>
                        )}
                        {selectedInstance.capabilities.resources.gpu_count && (
                          <div className="resource-item">
                            <span>GPU:</span>
                            <span>{selectedInstance.capabilities.resources.gpu_count} x {selectedInstance.capabilities.resources.gpu_type || 'GPU'}</span>
                          </div>
                        )}
                        {selectedInstance.capabilities.resources.storage_gb && (
                          <div className="resource-item">
                            <span>Storage:</span>
                            <span>{selectedInstance.capabilities.resources.storage_gb} GB</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {selectedInstance.metadata && Object.keys(selectedInstance.metadata).length > 0 && (
                <div className="details-section">
                  <h3>Metadata</h3>
                  <pre className="metadata-json">
                    {JSON.stringify(selectedInstance.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="refresh-info">
        <small>Auto-refreshes every 5 seconds</small>
      </div>

      {showLogsModal && selectedInstance && (
        <LogsModal
          instanceId={selectedInstance.instance_id}
          instanceName={selectedInstance.name}
          instanceType="compute"
          onClose={() => setShowLogsModal(false)}
        />
      )}
    </div>
  );
}

export default ComputeRegistry;

