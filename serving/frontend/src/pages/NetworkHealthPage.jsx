import { useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Activity, Clock, List, Map, Server, Store } from 'lucide-react'
import HealthPanel, { HealthStatusBar, HealthBreakdown } from '../components/health/HealthPanel'
import ComputeList from '../components/network/ComputeList'
import MarketplaceList from '../components/network/MarketplaceList'
import NetworkMap from '../components/network/NetworkMap'
import PendingConnections from '../components/network/PendingConnections'
import ComputeDetailModal from '../components/network/ComputeDetailModal'
import MarketplaceDetailModal from '../components/network/MarketplaceDetailModal'
import AuthModal from '../components/auth/AuthModal'
import Spinner from '../components/common/Spinner'
import useSystemHealth from '../hooks/useSystemHealth'
import useAuthTokens from '../hooks/useAuthTokens'
import './NetworkHealthPage.css'

function NetworkHealthPage() {
  const { health, loading, error, lastUpdated, refresh, connected, overallStatus } = useSystemHealth({
    pollInterval: 30000
  })
  const { systemStatus, getComponentAuth, refresh: refreshAuth } = useAuthTokens({ pollInterval: 30000 })

  const [viewMode, setViewMode] = useState('list') // 'list' or 'map'
  const [computeFilter, setComputeFilter] = useState(null)
  const [marketplaceFilter, setMarketplaceFilter] = useState(null)

  // For map view selections
  const [selectedCompute, setSelectedCompute] = useState(null)
  const [selectedMarketplace, setSelectedMarketplace] = useState(null)

  // Auth modal for serving
  const [showServingAuth, setShowServingAuth] = useState(false)

  const formatTime = (date) => {
    if (!date) return '-'
    return date.toLocaleTimeString()
  }

  if (loading && !health) {
    return (
      <div className="page">
        <header className="page-header">
          <h1 className="page-title">Network & Health</h1>
        </header>
        <div className="loading-container">
          <Spinner />
        </div>
      </div>
    )
  }

  // Calculate service statuses from health data
  const computeStats = health?.compute_registry || { total_instances: 0, by_status: {} }
  const marketplaceStats = health?.marketplace_registry || { total_marketplaces: 0, by_status: {} }

  const computeOnline = computeStats.by_status?.online || 0
  const computeDegraded = computeStats.by_status?.degraded || 0
  const computeOffline = computeStats.by_status?.offline || 0
  const computeTotal = computeStats.total_instances || 0

  const mpOnline = marketplaceStats.by_status?.online || 0
  const mpDegraded = marketplaceStats.by_status?.degraded || 0
  const mpOffline = marketplaceStats.by_status?.offline || 0
  const mpTotal = marketplaceStats.total_marketplaces || 0

  // Determine individual service statuses
  const servingStatus = health?.status || 'unknown'
  const redisStatus = health?.redis?.connected ? 'healthy' : 'offline'
  const marketplaceStatus = mpTotal === 0 ? 'unknown' :
    mpOffline > 0 ? 'degraded' :
    mpDegraded > 0 ? 'degraded' : 'healthy'

  // Serving auth status for the health panel
  const servingAuth = getComponentAuth('serving')
  const servingAuthLabel = servingAuth.status === 'active' ? 'Authorized' :
    servingAuth.status === 'expired' ? 'Expired' : 'Needed'
  const servingAuthStatus = servingAuth.status === 'active' ? 'healthy' :
    servingAuth.status === 'expired' ? 'offline' : 'degraded'

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-content">
          <h1 className="page-title">Network & Health</h1>
          <div className="health-meta">
            <span className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
              {connected ? 'Live' : 'Polling'}
            </span>
            <span className="last-updated">
              <Clock size={12} />
              {formatTime(lastUpdated)}
            </span>
          </div>
        </div>
        <button onClick={() => { refresh(); refreshAuth() }} className="refresh-btn" disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Pending Connections - shown at top when pending exist */}
      <PendingConnections />

      {/* Health Status Section - Always visible */}
      <section className="health-section">
        <header className="section-header">
          <h2 className="section-title">Health Status</h2>
        </header>
        <div className="health-summary">
          <div className={`overall-status-compact overall-status-${overallStatus}`}>
            <Activity size={18} />
            <div className="overall-status-text">
              <span className="overall-status-label">System</span>
              <span className="overall-status-value">{overallStatus}</span>
            </div>
          </div>
          <div className="health-services">
            <HealthPanel
              title="Redis"
              status={redisStatus}
              compact
              metrics={[]}
            />
            <HealthPanel
              title="Serving"
              status={servingStatus}
              compact
              metrics={[
                { value: health?.version || '-', label: 'Version' },
                {
                  value: servingAuthLabel,
                  label: 'Claude Auth',
                  onClick: () => setShowServingAuth(true),
                  status: servingAuthStatus
                }
              ]}
            />
            <HealthPanel
              title="Marketplace"
              status={marketplaceStatus}
              compact
              metrics={[
                { value: mpTotal, label: 'Total' }
              ]}
            />
          </div>
        </div>
      </section>

      {/* Network Section - With List/Map toggle */}
      <section className="network-section-unified">
        <header className="section-header">
          <h2 className="section-title">
            Compute Instances
          </h2>
          <div className="view-toggle">
            <button
              className={`view-toggle-btn ${viewMode === 'list' ? 'active' : ''}`}
              onClick={() => setViewMode('list')}
              title="List view"
            >
              <List size={16} />
            </button>
            <button
              className={`view-toggle-btn ${viewMode === 'map' ? 'active' : ''}`}
              onClick={() => setViewMode('map')}
              title="Map view"
            >
              <Map size={16} />
            </button>
          </div>
        </header>

        {viewMode === 'list' ? (
          <div className="network-grid">
            <section className="network-panel">
              <header className="network-panel-header">
                <Server size={16} className="network-panel-icon" />
                <h3 className="network-panel-title">Compute</h3>
              </header>
              <ComputeList
                statusFilter={computeFilter}
                onFilterChange={setComputeFilter}
              />
            </section>

            <section className="network-panel">
              <header className="network-panel-header">
                <Store size={16} className="network-panel-icon" />
                <Link to="/marketplace" className="network-panel-title-link">
                  <h3 className="network-panel-title">Marketplace</h3>
                </Link>
              </header>
              <MarketplaceList
                statusFilter={marketplaceFilter}
                onFilterChange={setMarketplaceFilter}
              />
            </section>
          </div>
        ) : (
          <NetworkMap
            onSelectCompute={setSelectedCompute}
            onSelectMarketplace={setSelectedMarketplace}
          />
        )}
      </section>

      {/* Detail modals for map view selections */}
      <ComputeDetailModal
        isOpen={!!selectedCompute}
        onClose={() => setSelectedCompute(null)}
        instanceId={selectedCompute}
      />
      <MarketplaceDetailModal
        isOpen={!!selectedMarketplace}
        onClose={() => setSelectedMarketplace(null)}
        marketplaceId={selectedMarketplace}
      />

      {/* Serving auth modal */}
      <AuthModal
        isOpen={showServingAuth}
        onClose={() => setShowServingAuth(false)}
        componentId="serving"
        componentName="Serving"
        componentType="serving"
        onAuthChange={refreshAuth}
      />
    </div>
  )
}

export default NetworkHealthPage
