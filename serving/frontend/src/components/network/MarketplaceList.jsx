import { useState } from 'react'
import { Store } from 'lucide-react'
import useMarketplace from '../../hooks/useMarketplace'
import MarketplaceCard from './MarketplaceCard'
import MarketplaceDetailModal from './MarketplaceDetailModal'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './Network.css'

function MarketplaceList({ statusFilter, onFilterChange }) {
  const { marketplaces, stats, loading, error, refresh } = useMarketplace({ status: statusFilter })
  const [selectedMarketplace, setSelectedMarketplace] = useState(null)

  const handleFilterClick = (status) => {
    onFilterChange(statusFilter === status ? null : status)
  }

  if (loading && !marketplaces.length) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={Store}
        title="Failed to load skill sources"
        description={error}
      />
    )
  }

  return (
    <div className="network-section">
      {stats && (
        <div className="stats-bar">
          <button
            className={`stat stat-clickable ${statusFilter === null ? 'stat-active' : ''}`}
            onClick={() => onFilterChange(null)}
          >
            <span className="stat-value">{stats.total_marketplaces || 0}</span>
            <span className="stat-label">Total</span>
          </button>
          <button
            className={`stat stat-clickable ${statusFilter === 'healthy' ? 'stat-active' : ''}`}
            onClick={() => handleFilterClick('healthy')}
          >
            <span className="stat-value stat-online">{stats.by_status?.healthy || 0}</span>
            <span className="stat-label">Healthy</span>
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
        </div>
      )}
      {marketplaces.length === 0 ? (
        <EmptyState
          icon={Store}
          title={statusFilter ? `No ${statusFilter} skill sources` : "No skill sources"}
          description={statusFilter ? "Try selecting a different status filter" : "Skill sources will appear here when they register with serving"}
        />
      ) : (
        <div className="card-grid">
          {marketplaces.map(marketplace => (
            <MarketplaceCard
              key={marketplace.marketplace_id}
              marketplace={marketplace}
              onClick={() => setSelectedMarketplace(marketplace.marketplace_id)}
            />
          ))}
        </div>
      )}

      <MarketplaceDetailModal
        isOpen={!!selectedMarketplace}
        onClose={() => setSelectedMarketplace(null)}
        marketplaceId={selectedMarketplace}
        onDeregister={refresh}
      />
    </div>
  )
}

export default MarketplaceList
