import { useState } from 'react'
import Modal from '../common/Modal'
import { AlertTriangle, Trash2 } from 'lucide-react'

function DeleteGoalConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  goal,
  commentCount = 0,
  loading = false
}) {
  const [error, setError] = useState(null)

  const handleConfirm = async () => {
    setError(null)
    try {
      await onConfirm()
    } catch (err) {
      setError(err.message || 'Failed to delete goal')
    }
  }

  if (!goal) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Delete Conversation?" width="420px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          padding: '12px',
          background: 'rgba(239, 68, 68, 0.1)',
          borderRadius: '8px',
          border: '1px solid rgba(239, 68, 68, 0.2)'
        }}>
          <AlertTriangle size={20} style={{ color: 'var(--error)', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <div style={{ fontWeight: 500, marginBottom: '4px' }}>This action cannot be undone</div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              The goal conversation will be marked as deleted and hidden from view.
            </div>
          </div>
        </div>

        <div style={{
          padding: '12px',
          background: 'var(--bg-surface)',
          borderRadius: '8px',
          border: '1px solid var(--border)'
        }}>
          <div style={{
            fontWeight: 500,
            marginBottom: '8px',
            color: 'var(--text)'
          }}>
            {goal.title}
          </div>
          {goal.description && (
            <div style={{
              fontSize: '13px',
              color: 'var(--text-secondary)',
              marginBottom: '8px',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden'
            }}>
              {goal.description}
            </div>
          )}
          <div style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            display: 'flex',
            gap: '12px'
          }}>
            <span>Priority: {goal.priority || 'P2'}</span>
            {commentCount > 0 && (
              <span style={{ fontWeight: 500 }}>
                {commentCount} comment{commentCount !== 1 ? 's' : ''} will be deleted
              </span>
            )}
          </div>
        </div>

        {error && (
          <div style={{
            padding: '8px 12px',
            background: 'rgba(239, 68, 68, 0.1)',
            borderRadius: '6px',
            color: 'var(--error)',
            fontSize: '13px'
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              background: 'var(--bg-hover)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '6px',
              background: 'var(--error)',
              color: 'white',
              fontSize: '13px',
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1
            }}
          >
            <Trash2 size={14} />
            {loading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export default DeleteGoalConfirmDialog
