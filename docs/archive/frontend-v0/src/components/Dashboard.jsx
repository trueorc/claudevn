import { useState, useEffect } from 'react';
import { getComputeInstances, getRegistryStats, getAggregatedCapabilities, getMarketplaces, getMarketplaceStats } from '../api';
import LogsModal from './LogsModal';
import './Dashboard.css';

function Dashboard() {
  const [stats, setStats] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [instances, setInstances] = useState([]);
  const [marketplaceStats, setMarketplaceStats] = useState(null);
  const [marketplaces, setMarketplaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [logsModal, setLogsModal] = useState(null);

  useEffect(() => {
    loadData();
    
    // Refresh every 10 seconds
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [statsData, capsData, instancesData, marketplaceStatsData, marketplacesData] = await Promise.all([
        getRegistryStats(),
        getAggregatedCapabilities(),
        getComputeInstances(),
        getMarketplaceStats(),
        getMarketplaces()
      ]);
      
      setStats(statsData);
      setCapabilities(capsData);
      setInstances(instancesData.instances || []);
      setMarketplaceStats(marketplaceStatsData);
      setMarketplaces(marketplacesData.marketplaces || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="dashboard loading">Loading dashboard...</div>;
  }

  if (error) {
    return (
      <div className="dashboard error">
        <h2>Error Loading Dashboard</h2>
        <p>{error}</p>
        <button onClick={loadData}>Retry</button>
      </div>
    );
  }

  const onlineInstances = instances.filter(i => i.status === 'online');
  const offlineInstances = instances.filter(i => i.status === 'offline');
  const degradedInstances = instances.filter(i => i.status === 'degraded');
  
  const healthyMarketplaces = marketplaces.filter(m => m.status === 'healthy');
  const degradedMarketplaces = marketplaces.filter(m => m.status === 'degraded');
  const offlineMarketplaces = marketplaces.filter(m => m.status === 'offline');

  return (
    <div className="dashboard">
      <h1>Serving Component Dashboard</h1>
      
      {/* Marketplace Overview */}
      <div className="section">
        <h2>🏪 Registered Marketplaces</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Total Marketplaces</h3>
            <div className="stat-value">{marketplaceStats?.total_marketplaces || 0}</div>
          </div>
          
          <div className="stat-card online">
            <h3>Healthy</h3>
            <div className="stat-value">{marketplaceStats?.healthy || 0}</div>
          </div>
          
          <div className="stat-card degraded">
            <h3>Degraded</h3>
            <div className="stat-value">{marketplaceStats?.degraded || 0}</div>
          </div>
          
          <div className="stat-card offline">
            <h3>Offline</h3>
            <div className="stat-value">{marketplaceStats?.offline || 0}</div>
          </div>
          
          <div className="stat-card">
            <h3>Total Agents</h3>
            <div className="stat-value">{marketplaceStats?.total_agents || 0}</div>
            <div className="stat-subtitle">across all marketplaces</div>
          </div>
          
          <div className="stat-card">
            <h3>Total Tools</h3>
            <div className="stat-value">{marketplaceStats?.total_tools || 0}</div>
            <div className="stat-subtitle">across all marketplaces</div>
          </div>
        </div>
        
        {/* Marketplace List */}
        {marketplaces.length > 0 && (
          <div className="marketplace-list">
            <h3>Active Marketplaces</h3>
            {marketplaces.slice(0, 5).map(marketplace => (
              <div key={marketplace.marketplace_id} className={`marketplace-card status-${marketplace.status}`}>
                <div className="marketplace-header">
                  <h4>{marketplace.name}</h4>
                  <span className={`status-badge ${marketplace.status}`}>
                    {marketplace.status === 'healthy' ? '🟢' : marketplace.status === 'degraded' ? '🟡' : '🔴'} {marketplace.status}
                  </span>
                </div>
                <div className="marketplace-details">
                  <div className="detail-item">
                    <span className="label">ID:</span>
                    <span className="value mono">{marketplace.marketplace_id}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Endpoint:</span>
                    <span className="value">{marketplace.endpoint}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Agents:</span>
                    <span className="value">{marketplace.capabilities?.agent_count || 0}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Tools:</span>
                    <span className="value">{marketplace.capabilities?.tool_count || 0}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Priority:</span>
                    <span className="value">{marketplace.priority}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Last Heartbeat:</span>
                    <span className="value">{new Date(marketplace.last_heartbeat).toLocaleString()}</span>
                  </div>
                </div>
                <div className="card-actions">
                  <button 
                    className="view-logs-btn"
                    onClick={() => setLogsModal({
                      id: marketplace.marketplace_id,
                      name: marketplace.name,
                      type: 'marketplace'
                    })}
                  >
                    📋 View Logs
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {marketplaces.length === 0 && (
          <div className="empty-state">
            <p>No marketplaces registered yet.</p>
            <p className="empty-state-hint">Marketplaces can register using the integrations UI at http://localhost:8001/integrations</p>
          </div>
        )}
      </div>
      
      {/* Compute Overview */}
      <div className="section">
        <h2>💻 Compute Instances</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Total Instances</h3>
            <div className="stat-value">{stats?.total_instances || 0}</div>
          </div>
          
          <div className="stat-card online">
            <h3>Online</h3>
            <div className="stat-value">{onlineInstances.length}</div>
          </div>
          
          <div className="stat-card degraded">
            <h3>Degraded</h3>
            <div className="stat-value">{degradedInstances.length}</div>
          </div>
          
          <div className="stat-card offline">
            <h3>Offline</h3>
            <div className="stat-value">{offlineInstances.length}</div>
          </div>
        </div>
      </div>

      {/* Virtual Compute Pool */}
      <div className="section">
        <h2>Virtual Compute Pool</h2>
        <div className="capabilities-grid">
          <div className="capability-card">
            <h3>Total Agents</h3>
            <div className="stat-value">{Object.keys(capabilities?.agents || {}).length}</div>
            <div className="stat-detail">
              {Object.entries(capabilities?.agents || {}).slice(0, 5).map(([agent, instances]) => (
                <div key={agent} className="capability-item">
                  <span className="capability-name">{agent}</span>
                  <span className="capability-count">{instances.length} instance{instances.length > 1 ? 's' : ''}</span>
                </div>
              ))}
              {Object.keys(capabilities?.agents || {}).length > 5 && (
                <div className="capability-item">
                  <span className="capability-name">...</span>
                  <span className="capability-count">and {Object.keys(capabilities.agents).length - 5} more</span>
                </div>
              )}
            </div>
          </div>
          
          <div className="capability-card">
            <h3>Total Tools</h3>
            <div className="stat-value">{Object.keys(capabilities?.tools || {}).length}</div>
            <div className="stat-detail">
              {Object.entries(capabilities?.tools || {}).slice(0, 5).map(([tool, instances]) => (
                <div key={tool} className="capability-item">
                  <span className="capability-name">{tool}</span>
                  <span className="capability-count">{instances.length} instance{instances.length > 1 ? 's' : ''}</span>
                </div>
              ))}
              {Object.keys(capabilities?.tools || {}).length > 5 && (
                <div className="capability-item">
                  <span className="capability-name">...</span>
                  <span className="capability-count">and {Object.keys(capabilities.tools).length - 5} more</span>
                </div>
              )}
            </div>
          </div>
          
          <div className="capability-card">
            <h3>Total Resources</h3>
            <div className="resource-list">
              {capabilities?.total_resources?.cpu_count && (
                <div className="resource-item">
                  <span className="resource-icon">🖥️</span>
                  <span className="resource-value">{capabilities.total_resources.cpu_count} CPUs</span>
                </div>
              )}
              {capabilities?.total_resources?.memory_gb && (
                <div className="resource-item">
                  <span className="resource-icon">💾</span>
                  <span className="resource-value">{capabilities.total_resources.memory_gb.toFixed(1)} GB RAM</span>
                </div>
              )}
              {capabilities?.total_resources?.gpu_count && (
                <div className="resource-item">
                  <span className="resource-icon">🎮</span>
                  <span className="resource-value">{capabilities.total_resources.gpu_count} GPUs</span>
                </div>
              )}
              {capabilities?.total_resources?.storage_gb && (
                <div className="resource-item">
                  <span className="resource-icon">💿</span>
                  <span className="resource-value">{capabilities.total_resources.storage_gb.toFixed(1)} GB Storage</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Compute Instances Detail */}
      <div className="section">
        <h2>Registered Compute Instances</h2>
        {instances.length === 0 ? (
          <div className="empty-state">
            <p>No compute instances registered yet.</p>
            <p className="empty-state-hint">Compute instances will auto-register when started with COMPUTE_REGISTER_ON_STARTUP=true</p>
          </div>
        ) : (
          <div className="compute-list">
            {instances.map((instance) => (
              <div key={instance.instance_id} className={`compute-card status-${instance.status}`}>
                <div className="compute-header">
                  <div className="compute-title">
                    <h4>{instance.name}</h4>
                    <span className="instance-id-badge">{instance.instance_id}</span>
                  </div>
                  <span className={`status-badge ${instance.status}`}>
                    {instance.status === 'online' ? '🟢' : instance.status === 'degraded' ? '🟡' : '🔴'} {instance.status}
                  </span>
                </div>
                
                <div className="compute-details">
                  <div className="detail-section">
                    <h5>Connection</h5>
                    <div className="detail-item">
                      <span className="label">Endpoint:</span>
                      <span className="value">{instance.endpoint}</span>
                    </div>
                    <div className="detail-item">
                      <span className="label">Version:</span>
                      <span className="value">{instance.version}</span>
                    </div>
                    <div className="detail-item">
                      <span className="label">Registered:</span>
                      <span className="value">{new Date(instance.registered_at).toLocaleString()}</span>
                    </div>
                    <div className="detail-item">
                      <span className="label">Last Heartbeat:</span>
                      <span className="value">{new Date(instance.last_heartbeat).toLocaleString()}</span>
                    </div>
                  </div>
                  
                  <div className="detail-section">
                    <h5>Capabilities</h5>
                    <div className="detail-item">
                      <span className="label">Agents:</span>
                      <span className="value badge">{instance.capabilities?.agents?.length || 0}</span>
                    </div>
                    <div className="detail-item">
                      <span className="label">Tools:</span>
                      <span className="value badge">{instance.capabilities?.tools?.length || 0}</span>
                    </div>
                    {instance.capabilities?.features && instance.capabilities.features.length > 0 && (
                      <div className="detail-item">
                        <span className="label">Features:</span>
                        <span className="value">
                          {instance.capabilities.features.map(f => (
                            <span key={f} className="feature-tag">{f}</span>
                          ))}
                        </span>
                      </div>
                    )}
                  </div>
                  
                  {instance.capabilities?.resources && (
                    <div className="detail-section">
                      <h5>Hardware Resources</h5>
                      <div className="resources-grid">
                        {instance.capabilities.resources.cpu_count && (
                          <div className="resource-item">
                            <span className="resource-icon">🖥️</span>
                            <span className="resource-value">{instance.capabilities.resources.cpu_count} CPUs</span>
                          </div>
                        )}
                        {instance.capabilities.resources.memory_gb && (
                          <div className="resource-item">
                            <span className="resource-icon">💾</span>
                            <span className="resource-value">{instance.capabilities.resources.memory_gb.toFixed(1)} GB</span>
                          </div>
                        )}
                        {instance.capabilities.resources.gpu_count && (
                          <div className="resource-item">
                            <span className="resource-icon">🎮</span>
                            <span className="resource-value">{instance.capabilities.resources.gpu_count} GPU</span>
                          </div>
                        )}
                        {instance.capabilities.resources.storage_gb && (
                          <div className="resource-item">
                            <span className="resource-icon">💿</span>
                            <span className="resource-value">{instance.capabilities.resources.storage_gb.toFixed(0)} GB</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {instance.metadata && Object.keys(instance.metadata).length > 0 && (
                    <div className="detail-section">
                      <h5>Metadata</h5>
                      {instance.metadata.platform && (
                        <div className="detail-item">
                          <span className="label">Platform:</span>
                          <span className="value">{instance.metadata.platform}</span>
                        </div>
                      )}
                      {instance.metadata.environment && (
                        <div className="detail-item">
                          <span className="label">Environment:</span>
                          <span className="value">{instance.metadata.environment}</span>
                        </div>
                      )}
                      {instance.metadata.location && (
                        <div className="detail-item">
                          <span className="label">Location:</span>
                          <span className="value">{instance.metadata.location}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="card-actions">
                  <button 
                    className="view-logs-btn"
                    onClick={() => setLogsModal({
                      id: instance.instance_id,
                      name: instance.name,
                      type: 'compute'
                    })}
                  >
                    📋 View Logs
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="refresh-info">
        <small>Dashboard auto-refreshes every 10 seconds</small>
      </div>

      {logsModal && (
        <LogsModal
          instanceId={logsModal.id}
          instanceName={logsModal.name}
          instanceType={logsModal.type}
          onClose={() => setLogsModal(null)}
        />
      )}
    </div>
  );
}

export default Dashboard;

