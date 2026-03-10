import { useState } from 'react'
import { Edit2, Trash2, Clock, GitBranch, Calendar } from 'lucide-react'
import Modal from '../common/Modal'
import { StatusBadge } from '../common/Badge'
import Badge from '../common/Badge'
import { updateIssueStatus, deleteIssue } from '../../api/workmap'
import './IssueDetailModal.css'

const statusOptions = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'ready', label: 'Ready' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'implemented', label: 'Implemented' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' }
]

// Mirrors backend VALID_TRANSITIONS in issue_ops_service.py
const validTransitions = {
  backlog: ['ready'],
  ready: ['in_progress', 'backlog'],
  in_progress: ['blocked', 'implemented', 'failed'],
  blocked: ['in_progress', 'ready'],
  implemented: ['done', 'in_progress'],
  done: ['backlog'],
  failed: ['ready', 'in_progress', 'backlog'],
}

// Transitions that require a reason
const reasonRequired = new Set(['done:backlog', 'failed:backlog'])

const priorityColors = {
  P0: 'error',
  P1: 'warning',
  P2: 'default',
  P3: 'info'
}

const typeLabels = {
  feature: 'Feature',
  bug: 'Bug',
  refactor: 'Refactor',
  docs: 'Documentation',
  test: 'Test'
}

const areaLabels = {
  api: 'API',
  database: 'Database',
  frontend: 'Frontend',
  infra: 'Infrastructure',
  other: 'Other'
}

function IssueDetailModal({ isOpen, onClose, issue, onEdit, onSuccess, viewOnly = false }) {
  const [statusLoading, setStatusLoading] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [error, setError] = useState(null)
  const [reasonPrompt, setReasonPrompt] = useState(null) // { targetStatus }
  const [reasonText, setReasonText] = useState('')

  if (!issue) return null

  const allowedNextStatuses = validTransitions[issue.status] || []

  const handleStatusChange = async (newStatus) => {
    if (viewOnly) return
    if (newStatus === issue.status) return

    // Check if reason is required
    const key = `${issue.status}:${newStatus}`
    if (reasonRequired.has(key)) {
      setReasonPrompt({ targetStatus: newStatus })
      setReasonText('')
      return
    }

    await executeStatusChange(newStatus)
  }

  const executeStatusChange = async (newStatus, reason = null) => {
    setStatusLoading(true)
    setError(null)

    try {
      await updateIssueStatus(issue.issue_id, newStatus, reason)
      setReasonPrompt(null)
      setReasonText('')
      onSuccess?.()
    } catch (err) {
      setError(err.message || 'Failed to update status')
    } finally {
      setStatusLoading(false)
    }
  }

  const handleReasonSubmit = () => {
    if (!reasonText.trim()) return
    executeStatusChange(reasonPrompt.targetStatus, reasonText.trim())
  }

  const handleDelete = async () => {
    if (!deleteConfirm) {
      setDeleteConfirm(true)
      return
    }

    try {
      await deleteIssue(issue.issue_id)
      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to delete issue')
      setDeleteConfirm(false)
    }
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Issue #${issue.issue_id || issue.id}`}
      width="600px"
    >
      <div className="issue-detail">
        {error && (
          <div className="detail-error">{error}</div>
        )}

        <div className="detail-header">
          <h3 className="detail-title">{issue.title}</h3>
          {!viewOnly && (
            <div className="detail-actions">
              <button
                className="detail-action-btn"
                onClick={() => onEdit?.(issue)}
                title="Edit Issue"
              >
                <Edit2 size={14} />
              </button>
              <button
                className={`detail-action-btn ${deleteConfirm ? 'confirm' : ''}`}
                onClick={handleDelete}
                title={deleteConfirm ? 'Click again to confirm' : 'Delete Issue'}
              >
                <Trash2 size={14} />
                {deleteConfirm && <span>Confirm?</span>}
              </button>
            </div>
          )}
        </div>

        <div className="detail-badges">
          <StatusBadge status={issue.status} />
          {issue.priority && (
            <Badge variant={priorityColors[issue.priority] || 'default'}>
              {issue.priority}
            </Badge>
          )}
          {issue.issue_type && (
            <Badge variant="default">{typeLabels[issue.issue_type] || issue.issue_type}</Badge>
          )}
          {issue.area && (
            <Badge variant="default">{areaLabels[issue.area] || issue.area}</Badge>
          )}
          {issue.release_id && (
            <Badge variant="info">
              <Calendar size={10} style={{ marginRight: '4px' }} />
              {issue.release_name || issue.release_id}
            </Badge>
          )}
        </div>

        {!viewOnly && (
          <div className="detail-section">
            <label className="detail-label">Status</label>
            <div className="status-buttons">
              {statusOptions
                .filter(opt =>
                  opt.value === issue.status || allowedNextStatuses.includes(opt.value)
                )
                .map(opt => (
                  <button
                    key={opt.value}
                    className={`status-btn ${issue.status === opt.value ? 'active' : ''}`}
                    onClick={() => handleStatusChange(opt.value)}
                    disabled={statusLoading || opt.value === issue.status}
                  >
                    {opt.label}
                  </button>
                ))}
            </div>
            {reasonPrompt && (
              <div className="reason-prompt">
                <label className="detail-label">
                  Reason for moving back to Backlog
                </label>
                <textarea
                  className="reason-textarea"
                  value={reasonText}
                  onChange={(e) => setReasonText(e.target.value)}
                  placeholder="Explain why this issue needs to be reworked..."
                  rows={3}
                  autoFocus
                />
                <div className="reason-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => { setReasonPrompt(null); setReasonText('') }}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleReasonSubmit}
                    disabled={!reasonText.trim() || statusLoading}
                  >
                    Confirm
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="detail-section">
          <label className="detail-label">Description</label>
          <div className="detail-description">
            {issue.description || 'No description provided'}
          </div>
        </div>

        {issue.required_skills && issue.required_skills.length > 0 && (
          <div className="detail-section">
            <label className="detail-label">Required Skills</label>
            <div className="detail-skills">
              {issue.required_skills.map(skill => (
                <span key={skill} className="skill-badge">{skill}</span>
              ))}
            </div>
          </div>
        )}

        {issue.depends_on && issue.depends_on.length > 0 && (
          <div className="detail-section">
            <label className="detail-label">Dependencies</label>
            <div className="detail-dependencies">
              {issue.depends_on.map(depId => (
                <span key={depId} className="dep-badge">#{depId}</span>
              ))}
            </div>
          </div>
        )}

        {issue.blocks && issue.blocks.length > 0 && (
          <div className="detail-section">
            <label className="detail-label">Blocks</label>
            <div className="detail-dependencies">
              {issue.blocks.map(blockId => (
                <span key={blockId} className="dep-badge blocked">#{blockId}</span>
              ))}
            </div>
          </div>
        )}

        {issue.result && (
          <div className="detail-section">
            <label className="detail-label">Result</label>
            <div className="detail-result">
              {issue.result.branch && (
                <div className="result-item">
                  <GitBranch size={12} />
                  <span>{issue.result.branch}</span>
                </div>
              )}
              {issue.result.summary && (
                <p className="result-summary">{issue.result.summary}</p>
              )}
            </div>
          </div>
        )}

        <div className="detail-meta">
          <div className="meta-item">
            <Clock size={12} />
            <span>Created: {formatDate(issue.created_at)}</span>
          </div>
          {issue.started_at && (
            <div className="meta-item">
              <Clock size={12} />
              <span>Started: {formatDate(issue.started_at)}</span>
            </div>
          )}
          {issue.completed_at && (
            <div className="meta-item">
              <Clock size={12} />
              <span>Completed: {formatDate(issue.completed_at)}</span>
            </div>
          )}
          {issue.assigned_compute_id && (
            <div className="meta-item">
              <span>Assigned to: {issue.assigned_compute_id}</span>
            </div>
          )}
        </div>

        <div className="detail-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          {!viewOnly && (
            <button className="btn btn-primary" onClick={() => onEdit?.(issue)}>
              Edit Issue
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default IssueDetailModal
