import { useState, useEffect, useCallback } from 'react'
import { ShieldAlert, Check, X, RefreshCw } from 'lucide-react'
import { request } from '../../api/index'
import { useToast } from '../../hooks/useToast'
import ConfirmDialog from '../common/ConfirmDialog'
import './PendingConnections.css'

export default function PendingConnections() {
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [rejectingId, setRejectingId] = useState(null)
  const [rejectLoading, setRejectLoading] = useState(false)
  const [approvingId, setApprovingId] = useState(null)
  const toast = useToast()

  const fetchPending = useCallback(async () => {
    try {
      const data = await request('/compute/pending')
      setPending(data.pending || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPending()
    // Poll every 10 seconds for new connections
    const interval = setInterval(fetchPending, 10000)
    return () => clearInterval(interval)
  }, [fetchPending])

  const handleApprove = async (instanceId) => {
    setApprovingId(instanceId)
    try {
      await request(`/compute/${instanceId}/approve`, { method: 'POST' })
      toast.success(`Approved ${instanceId}`)
      fetchPending()
    } catch (err) {
      toast.error(err.message || 'Failed to approve')
    } finally {
      setApprovingId(null)
    }
  }

  const handleReject = async () => {
    if (!rejectingId) return
    setRejectLoading(true)
    try {
      await request(`/compute/${rejectingId}/reject`, { method: 'POST' })
      toast.success(`Rejected ${rejectingId}`)
      setRejectingId(null)
      fetchPending()
    } catch (err) {
      toast.error(err.message || 'Failed to reject')
    } finally {
      setRejectLoading(false)
    }
  }

  if (loading) return null
  if (error) return null
  if (pending.length === 0) return null

  return (
    <div className="pending-connections">
      <div className="pending-header">
        <ShieldAlert size={16} className="pending-icon" />
        <span className="pending-title">
          Pending Connections ({pending.length})
        </span>
        <button className="btn-icon" onClick={fetchPending} title="Refresh">
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="pending-list">
        {pending.map((conn) => (
          <div key={conn.instance_id} className="pending-item">
            <div className="pending-info">
              <span className="pending-name">{conn.name || conn.instance_id}</span>
              <span className="pending-meta">
                {conn.capabilities.length > 0 && (
                  <span className="pending-caps">{conn.capabilities.join(', ')}</span>
                )}
                {conn.labels.length > 0 && (
                  <span className="pending-labels">
                    {conn.labels.map(l => (
                      <span key={l} className="pending-label-tag">{l}</span>
                    ))}
                  </span>
                )}
                {conn.pending_since && (
                  <span className="pending-time">
                    since {new Date(conn.pending_since).toLocaleTimeString()}
                  </span>
                )}
              </span>
            </div>
            <div className="pending-actions">
              <button
                className="pending-approve"
                onClick={() => handleApprove(conn.instance_id)}
                disabled={approvingId === conn.instance_id}
                title="Approve"
              >
                <Check size={14} />
                {approvingId === conn.instance_id ? 'Approving...' : 'Approve'}
              </button>
              <button
                className="pending-deny"
                onClick={() => setRejectingId(conn.instance_id)}
                title="Deny"
              >
                <X size={14} /> Deny
              </button>
            </div>
          </div>
        ))}
      </div>

      {rejectingId && (
        <ConfirmDialog
          title="Deny Connection"
          message={`Deny connection from ${rejectingId}? The compute instance will be disconnected.`}
          confirmLabel="Deny"
          confirmVariant="danger"
          loading={rejectLoading}
          onConfirm={handleReject}
          onCancel={() => setRejectingId(null)}
        />
      )}
    </div>
  )
}
