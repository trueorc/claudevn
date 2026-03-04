import { useState, useEffect } from 'react'
import { Check, Globe } from 'lucide-react'
import Modal from '../common/Modal'
import { getProjects } from '../../api/projects'
import './ApprovalModal.css'

export default function ApprovalModal({ instance, onConfirm, onClose, loading }) {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState([])
  const [allProjects, setAllProjects] = useState(false)
  const [fetchError, setFetchError] = useState(null)
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function fetchProjects() {
      try {
        const items = await getProjects()
        if (!cancelled) {
          setProjects(items)
          setFetchError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setFetchError(err.message)
        }
      } finally {
        if (!cancelled) setFetching(false)
      }
    }
    fetchProjects()
    return () => { cancelled = true }
  }, [])

  const handleToggle = (projectId) => {
    setSelected(prev =>
      prev.includes(projectId)
        ? prev.filter(id => id !== projectId)
        : [...prev, projectId]
    )
  }

  const handleAllToggle = () => {
    const next = !allProjects
    setAllProjects(next)
    if (next) {
      setSelected([])
    }
  }

  const handleConfirm = () => {
    const projectIds = allProjects ? ['*'] : selected
    onConfirm(projectIds)
  }

  const canConfirm = allProjects || selected.length > 0

  return (
    <Modal isOpen={true} onClose={onClose} title="Approve Compute Instance" width="480px">
      <div className="approval-modal">
        <div className="approval-instance">
          <span className="approval-instance-label">Instance</span>
          <span className="approval-instance-name">
            {instance.name || instance.instance_id}
          </span>
        </div>

        <div className="approval-section">
          <label className="approval-section-label">Assign Projects</label>
          <p className="approval-section-hint">
            Select which projects this instance can receive work from.
            Without any projects, the instance will be benched (no work assigned).
          </p>

          <label className="approval-option approval-option-all">
            <input
              type="checkbox"
              checked={allProjects}
              onChange={handleAllToggle}
              className="approval-checkbox"
            />
            <Globe size={14} />
            <span>All projects</span>
            <span className="approval-option-hint">Receives work from any project</span>
          </label>

          {fetching && (
            <div className="approval-loading">Loading projects...</div>
          )}

          {fetchError && (
            <div className="approval-error">
              Failed to load projects: {fetchError}
            </div>
          )}

          {!fetching && !fetchError && projects.length === 0 && (
            <div className="approval-empty">
              No projects found. Use "All projects" or approve without assignment.
            </div>
          )}

          {!fetching && projects.length > 0 && (
            <div className="approval-project-list">
              {projects.map(project => (
                <label
                  key={project.project_id}
                  className={`approval-option ${allProjects ? 'approval-option-disabled' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={allProjects || selected.includes(project.project_id)}
                    disabled={allProjects}
                    onChange={() => handleToggle(project.project_id)}
                    className="approval-checkbox"
                  />
                  <span className="approval-project-name">{project.name}</span>
                  {project.description && (
                    <span className="approval-project-desc">{project.description}</span>
                  )}
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="approval-actions">
          <button
            className="btn btn-secondary"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            className="btn btn-approve"
            onClick={handleConfirm}
            disabled={loading || !canConfirm}
          >
            <Check size={14} />
            {loading ? 'Approving...' : 'Approve'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
