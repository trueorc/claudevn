import { useState } from 'react'
import Modal from '../common/Modal'
import { deleteProject } from '../../api/projects'
import '../common/Modal.css'

function DeleteProjectModal({ isOpen, onClose, onSuccess, project }) {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)

  const handleDelete = async () => {
    if (!project) return

    setDeleting(true)
    setError(null)

    try {
      await deleteProject(project.project_id)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to delete project')
    } finally {
      setDeleting(false)
    }
  }

  if (!project) return null

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Delete Project"
    >
      <p style={{ marginBottom: 'var(--space-md)', color: 'var(--text-secondary)' }}>
        Are you sure you want to delete <strong style={{ color: 'var(--text)' }}>{project.name}</strong>?
        This action cannot be undone.
      </p>

      {error && (
        <div style={{ color: 'var(--status-offline)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-md)' }}>
          {error}
        </div>
      )}

      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? 'Deleting...' : 'Delete Project'}
        </button>
      </div>
    </Modal>
  )
}

export default DeleteProjectModal
