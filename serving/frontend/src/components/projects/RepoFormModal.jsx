import { useState, useEffect } from 'react'
import Modal from '../common/Modal'
import { addRepoToProject, createInternalRepo } from '../../api/projects'
import '../common/Modal.css'

function RepoFormModal({ isOpen, onClose, onSuccess, projectId }) {
  const [mode, setMode] = useState('create')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [defaultBranch, setDefaultBranch] = useState('main')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (isOpen) {
      setMode('create')
      setName('')
      setUrl('')
      setDefaultBranch('main')
      setError(null)
    }
  }, [isOpen])

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!name.trim()) {
      setError('Repository name is required')
      return
    }

    if (mode === 'link' && !url.trim()) {
      setError('Repository URL is required')
      return
    }

    setSaving(true)
    setError(null)

    try {
      if (mode === 'create') {
        await createInternalRepo(projectId, {
          name: name.trim(),
          default_branch: defaultBranch.trim() || 'main'
        })
      } else {
        await addRepoToProject(projectId, {
          name: name.trim(),
          url: url.trim(),
          default_branch: defaultBranch.trim() || 'main'
        })
      }
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to add repository')
    } finally {
      setSaving(false)
    }
  }

  const tabStyle = (active) => ({
    padding: 'var(--space-sm) var(--space-md)',
    border: 'none',
    borderBottom: active ? '2px solid var(--accent-primary)' : '2px solid transparent',
    background: 'none',
    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
    cursor: 'pointer',
    fontWeight: active ? '600' : '400',
    fontSize: 'var(--font-size-sm)'
  })

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Repository">
      <div style={{ display: 'flex', gap: 'var(--space-xs)', marginBottom: 'var(--space-lg)', borderBottom: '1px solid var(--border-subtle)' }}>
        <button
          type="button"
          style={tabStyle(mode === 'create')}
          onClick={() => { setMode('create'); setError(null) }}
        >
          Create New
        </button>
        <button
          type="button"
          style={tabStyle(mode === 'link')}
          onClick={() => { setMode('link'); setError(null) }}
        >
          Link External
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label" htmlFor="repo-name">
            Name
          </label>
          <input
            id="repo-name"
            type="text"
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-repo"
            autoFocus
          />
        </div>

        {mode === 'link' && (
          <div className="form-group">
            <label className="form-label" htmlFor="repo-url">
              URL
            </label>
            <input
              id="repo-url"
              type="text"
              className="form-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/org/repo.git"
            />
          </div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="repo-branch">
            Default Branch
          </label>
          <input
            id="repo-branch"
            type="text"
            className="form-input"
            value={defaultBranch}
            onChange={(e) => setDefaultBranch(e.target.value)}
            placeholder="main"
          />
        </div>

        {error && (
          <div style={{ color: 'var(--status-offline)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-md)' }}>
            {error}
          </div>
        )}

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving
              ? (mode === 'create' ? 'Creating...' : 'Adding...')
              : (mode === 'create' ? 'Create Repository' : 'Add Repository')
            }
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default RepoFormModal
