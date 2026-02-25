import { useState, useEffect } from 'react'
import Modal from '../common/Modal'
import { addRepoToProject, createInternalRepo } from '../../api/projects'
import { useSSHKeys } from '../../hooks/useSSHKeys'
import { useToast } from '../../hooks/useToast'
import '../common/Modal.css'

function RepoFormModal({ isOpen, onClose, onSuccess, projectId }) {
  const [mode, setMode] = useState('create')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [defaultBranch, setDefaultBranch] = useState('main')
  const [sshKeyId, setSshKeyId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [showGenerateKey, setShowGenerateKey] = useState(false)
  const [keyDescription, setKeyDescription] = useState('')
  const [generatingKey, setGeneratingKey] = useState(false)

  const { keys, loading: keysLoading, generate: generateKey, refresh: refreshKeys } = useSSHKeys()
  const toast = useToast()

  useEffect(() => {
    if (isOpen) {
      setMode('create')
      setName('')
      setUrl('')
      setDefaultBranch('main')
      setSshKeyId('')
      setError(null)
      setShowGenerateKey(false)
      setKeyDescription('')
      refreshKeys()
    }
  }, [isOpen, refreshKeys])

  const handleGenerateKey = async () => {
    setGeneratingKey(true)
    try {
      const result = await generateKey(keyDescription.trim())
      setSshKeyId(result.key_id)
      setShowGenerateKey(false)
      setKeyDescription('')
      toast.success('SSH key generated')
    } catch (err) {
      toast.error(err.message || 'Failed to generate key')
    } finally {
      setGeneratingKey(false)
    }
  }

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
          default_branch: defaultBranch.trim() || 'main',
          ssh_key_id: sshKeyId || undefined
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
              placeholder="git@github.com:org/repo.git"
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

        {mode === 'link' && (
          <div className="form-group">
            <label className="form-label" htmlFor="repo-ssh-key">
              SSH Key
            </label>
            <select
              id="repo-ssh-key"
              className="form-input"
              value={sshKeyId}
              onChange={(e) => setSshKeyId(e.target.value)}
            >
              <option value="">None (no authentication)</option>
              {keysLoading && <option disabled>Loading keys...</option>}
              {keys.map((key) => (
                <option key={key.key_id} value={key.key_id}>
                  {key.key_id}{key.description ? ` - ${key.description}` : ''}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setShowGenerateKey(!showGenerateKey)}
              style={{
                marginTop: 'var(--space-xs)',
                background: 'none',
                border: 'none',
                color: 'var(--primary)',
                fontSize: 'var(--font-size-xs)',
                cursor: 'pointer',
                padding: 0
              }}
            >
              + Generate New Key
            </button>
            <p style={{
              fontSize: 'var(--font-size-xs)',
              color: 'var(--text-muted)',
              marginTop: 'var(--space-xs)'
            }}>
              Required for push access. Add the public key as a deploy key on the remote repository.
            </p>

            {showGenerateKey && (
              <div style={{
                marginTop: 'var(--space-sm)',
                padding: 'var(--space-sm)',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)'
              }}>
                <input
                  type="text"
                  className="form-input"
                  value={keyDescription}
                  onChange={(e) => setKeyDescription(e.target.value)}
                  placeholder="Key description (e.g., GitHub deploy key)"
                  style={{ marginBottom: 'var(--space-sm)' }}
                />
                <div style={{ display: 'flex', gap: 'var(--space-xs)', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => { setShowGenerateKey(false); setKeyDescription('') }}
                    style={{ padding: '2px 8px', fontSize: 'var(--font-size-xs)' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleGenerateKey}
                    disabled={generatingKey}
                    style={{ padding: '2px 8px', fontSize: 'var(--font-size-xs)' }}
                  >
                    {generatingKey ? 'Generating...' : 'Generate'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

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
              ? (mode === 'create' ? 'Creating...' : 'Linking...')
              : (mode === 'create' ? 'Create Repository' : 'Link Repository')
            }
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default RepoFormModal
