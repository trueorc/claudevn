import { useState } from 'react'
import { Server } from 'lucide-react'
import useCompute from '../../hooks/useCompute'
import useAuthTokens from '../../hooks/useAuthTokens'
import ComputeCard from './ComputeCard'
import ComputeDetailModal from './ComputeDetailModal'
import AuthModal from '../auth/AuthModal'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './Network.css'

function ComputeList({ statusFilter, onFilterChange }) {
  const { instances, stats, loading, error, refresh } = useCompute({ status: statusFilter })
  const { getComponentAuth, systemStatus, refresh: refreshAuth } = useAuthTokens()
  const [selectedInstance, setSelectedInstance] = useState(null)
  const [authTarget, setAuthTarget] = useState(null)

  const handleFilterClick = (status) => {
    onFilterChange(statusFilter === status ? null : status)
  }

  const handleAuthChange = () => {
    refreshAuth()
  }

  if (loading && !instances.length) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={Server}
        title="Failed to load compute instances"
        description={error}
      />
    )
  }

  // Auth summary stats
  const authSummary = systemStatus && systemStatus.status !== 'disabled'
    ? `${systemStatus.compute_authorized || 0}/${instances.length} authorized`
    : null

  return (
    <div className="network-section">
      {stats && (
        <div className="stats-bar">
          <button
            className={`stat stat-clickable ${statusFilter === null ? 'stat-active' : ''}`}
            onClick={() => onFilterChange(null)}
          >
            <span className="stat-value">{stats.total_instances || 0}</span>
            <span className="stat-label">Total</span>
          </button>
          <button
            className={`stat stat-clickable ${statusFilter === 'online' ? 'stat-active' : ''}`}
            onClick={() => handleFilterClick('online')}
          >
            <span className="stat-value stat-online">{stats.by_status?.online || 0}</span>
            <span className="stat-label">Online</span>
          </button>
          <button
            className={`stat stat-clickable ${statusFilter === 'degraded' ? 'stat-active' : ''}`}
            onClick={() => handleFilterClick('degraded')}
          >
            <span className="stat-value stat-degraded">{stats.by_status?.degraded || 0}</span>
            <span className="stat-label">Degraded</span>
          </button>
          <button
            className={`stat stat-clickable ${statusFilter === 'offline' ? 'stat-active' : ''}`}
            onClick={() => handleFilterClick('offline')}
          >
            <span className="stat-value stat-offline">{stats.by_status?.offline || 0}</span>
            <span className="stat-label">Offline</span>
          </button>
          {authSummary && (
            <span className="stat">
              <span className="stat-value">{authSummary}</span>
              <span className="stat-label">Auth</span>
            </span>
          )}
        </div>
      )}
      {instances.length === 0 ? (
        <EmptyState
          icon={Server}
          title={statusFilter ? `No ${statusFilter} compute instances` : "No compute instances"}
          description={statusFilter ? "Try selecting a different status filter" : "Compute instances will appear here when they register with serving"}
        />
      ) : (
        <div className="card-grid">
          {instances.map(instance => (
            <ComputeCard
              key={instance.instance_id}
              instance={instance}
              authInfo={getComponentAuth(instance.instance_id)}
              onClick={() => setSelectedInstance(instance.instance_id)}
              onAuthClick={() => setAuthTarget({
                id: instance.instance_id,
                name: instance.name || instance.instance_id,
                type: 'compute'
              })}
            />
          ))}
        </div>
      )}

      <ComputeDetailModal
        isOpen={!!selectedInstance}
        onClose={() => setSelectedInstance(null)}
        instanceId={selectedInstance}
        onDeregister={refresh}
      />

      <AuthModal
        isOpen={!!authTarget}
        onClose={() => setAuthTarget(null)}
        componentId={authTarget?.id}
        componentName={authTarget?.name}
        componentType={authTarget?.type}
        onAuthChange={handleAuthChange}
      />
    </div>
  )
}

export default ComputeList
