import { useState, useEffect } from 'react'
import { Store } from 'lucide-react'
import Modal from '../common/Modal'
import ConfirmDialog from '../common/ConfirmDialog'
import { StatusBadge } from '../common/Badge'
import { getMarketplace, deregisterMarketplace } from '../../api/marketplace'
import '../common/Modal.css'
import './Network.css'

function MarketplaceDetailModal({ isOpen, onClose, marketplaceId, onDeregister }) {
  const [marketplace, setMarketplace] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showConfirm, setShowConfirm] = useState(false)
  const [deregistering, setDeregistering] = useState(false)

  useEffect(() => {
    if (isOpen && marketplaceId) {
      setLoading(true)
      setError(null)
      getMarketplace(marketplaceId)
        .then(setMarketplace)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }
  }, [isOpen, marketplaceId])

  const handleDeregister = async () => {
    setDeregistering(true)
    try {
      await deregisterMarketplace(marketplaceId)
      setShowConfirm(false)
      onClose()
      onDeregister?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeregistering(false)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} title="Skill Source" width="550px">
        {loading ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading...
          </div>
        ) : error ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--status-offline)' }}>
            {error}
          </div>
        ) : marketplace ? (
          <div className="detail-content">
            <div className="detail-header">
              <Store size={20} style={{ color: 'var(--text-muted)' }} />
              <span className="detail-name">{marketplace.name || marketplace.marketplace_id}</span>
              <StatusBadge status={marketplace.status} />
            </div>

            <div className="detail-section">
              <div className="detail-row">
                <span className="detail-label">Source ID</span>
                <span className="detail-value mono">{marketplace.marketplace_id}</span>
              </div>
              {marketplace.endpoint && (
                <div className="detail-row">
                  <span className="detail-label">Endpoint</span>
                  <span className="detail-value mono">{marketplace.endpoint}</span>
                </div>
              )}
              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className="detail-value">{marketplace.status}</span>
              </div>
              {marketplace.last_heartbeat && (
                <div className="detail-row">
                  <span className="detail-label">Last Heartbeat</span>
                  <span className="detail-value">{new Date(marketplace.last_heartbeat).toLocaleString()}</span>
                </div>
              )}
              {marketplace.registered_at && (
                <div className="detail-row">
                  <span className="detail-label">Registered</span>
                  <span className="detail-value">{new Date(marketplace.registered_at).toLocaleString()}</span>
                </div>
              )}
            </div>

            {marketplace.capabilities && (
              <div className="detail-section">
                <h4 className="detail-section-title">Capabilities</h4>
                {marketplace.capabilities.agent_count !== undefined && (
                  <div className="detail-row">
                    <span className="detail-label">Agent Count</span>
                    <span className="detail-value">{marketplace.capabilities.agent_count}</span>
                  </div>
                )}
                {marketplace.capabilities.tool_count !== undefined && (
                  <div className="detail-row">
                    <span className="detail-label">Tool Count</span>
                    <span className="detail-value">{marketplace.capabilities.tool_count}</span>
                  </div>
                )}
                {marketplace.capabilities.supported_protocols?.length > 0 && (
                  <div className="detail-row">
                    <span className="detail-label">Protocols</span>
                    <span className="detail-value">{marketplace.capabilities.supported_protocols.join(', ')}</span>
                  </div>
                )}
              </div>
            )}

            {marketplace.metadata && Object.keys(marketplace.metadata).length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title">Metadata</h4>
                {Object.entries(marketplace.metadata).map(([key, value]) => (
                  <div className="detail-row" key={key}>
                    <span className="detail-label">{key}</span>
                    <span className="detail-value">{String(value)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="detail-actions">
              <button
                onClick={() => setShowConfirm(true)}
                className="btn btn-danger"
              >
                Disconnect Skill Source
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleDeregister}
        title="Disconnect Skill Source"
        message={`Are you sure you want to disconnect "${marketplace?.name || marketplaceId}"? This will remove it from the serving network.`}
        confirmText="Disconnect"
        variant="danger"
        loading={deregistering}
      />
    </>
  )
}

export default MarketplaceDetailModal
