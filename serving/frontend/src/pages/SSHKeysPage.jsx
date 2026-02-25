import { useState } from 'react'
import { Plus, Key, Trash2, Copy, Eye, Check } from 'lucide-react'
import { useSSHKeys } from '../hooks/useSSHKeys'
import { useToast } from '../hooks/useToast'
import ConfirmDialog from '../components/common/ConfirmDialog'
import './SSHKeysPage.css'

function SSHKeysPage() {
  const { keys, loading, error, generate, remove, getKey } = useSSHKeys()
  const toast = useToast()

  const [generating, setGenerating] = useState(false)
  const [description, setDescription] = useState('')
  const [showGenerateForm, setShowGenerateForm] = useState(false)
  const [generatedKey, setGeneratedKey] = useState(null)
  const [viewingKey, setViewingKey] = useState(null)
  const [viewingPublicKey, setViewingPublicKey] = useState(null)
  const [deletingKey, setDeletingKey] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [copiedId, setCopiedId] = useState(null)

  const handleGenerate = async (e) => {
    e.preventDefault()
    setGenerating(true)
    try {
      const result = await generate(description.trim())
      setGeneratedKey(result)
      setDescription('')
      setShowGenerateForm(false)
      toast.success('SSH key generated')
    } catch (err) {
      toast.error(err.message || 'Failed to generate key')
    } finally {
      setGenerating(false)
    }
  }

  const handleViewKey = async (keyId) => {
    if (viewingKey === keyId) {
      setViewingKey(null)
      setViewingPublicKey(null)
      return
    }
    try {
      const data = await getKey(keyId)
      setViewingKey(keyId)
      setViewingPublicKey(data.public_key)
    } catch (err) {
      toast.error('Failed to load public key')
    }
  }

  const handleDelete = async () => {
    if (!deletingKey) return
    setDeleteLoading(true)
    try {
      const result = await remove(deletingKey.key_id)
      if (result.referencing_repos?.length > 0) {
        toast.warning(`Key deleted. Note: ${result.referencing_repos.length} repo(s) still reference this key.`)
      } else {
        toast.success('SSH key deleted')
      }
      if (viewingKey === deletingKey.key_id) {
        setViewingKey(null)
        setViewingPublicKey(null)
      }
      if (generatedKey?.key_id === deletingKey.key_id) {
        setGeneratedKey(null)
      }
      setDeletingKey(null)
    } catch (err) {
      toast.error(err.message || 'Failed to delete key')
    } finally {
      setDeleteLoading(false)
    }
  }

  const copyToClipboard = async (text, id) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch {
      toast.error('Failed to copy to clipboard')
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">SSH Keys</h1>
        <button
          onClick={() => setShowGenerateForm(!showGenerateForm)}
          className="ssh-btn-generate"
        >
          <Plus size={14} />
          Generate New Key
        </button>
      </header>

      {showGenerateForm && (
        <div className="ssh-generate-form-card">
          <form onSubmit={handleGenerate} className="ssh-generate-form">
            <div className="form-group">
              <label className="form-label" htmlFor="key-description">
                Description
              </label>
              <input
                id="key-description"
                type="text"
                className="form-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g., GitHub deploy key"
                autoFocus
              />
            </div>
            <div className="ssh-generate-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => { setShowGenerateForm(false); setDescription('') }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={generating}
              >
                {generating ? 'Generating...' : 'Generate'}
              </button>
            </div>
          </form>
        </div>
      )}

      {generatedKey && (
        <div className="ssh-generated-key-card">
          <div className="ssh-generated-header">
            <Key size={14} />
            <span>New Key Generated: {generatedKey.key_id}</span>
          </div>
          <p className="ssh-generated-hint">
            Add this public key as a deploy key with write access on your repository host.
          </p>
          <div className="ssh-public-key-box">
            <code>{generatedKey.public_key}</code>
            <button
              className="ssh-copy-btn"
              onClick={() => copyToClipboard(generatedKey.public_key, 'generated')}
              title="Copy public key"
            >
              {copiedId === 'generated' ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          <button
            className="ssh-dismiss-btn"
            onClick={() => setGeneratedKey(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="ssh-error">
          Failed to load SSH keys: {error}
        </div>
      )}

      {loading ? (
        <div className="ssh-loading">Loading SSH keys...</div>
      ) : keys.length === 0 ? (
        <div className="ssh-empty">
          <Key size={24} strokeWidth={1} />
          <p>No SSH keys generated yet</p>
          <p className="ssh-empty-hint">Generate a key to enable linking external repositories with push access.</p>
        </div>
      ) : (
        <div className="ssh-keys-table-wrapper">
          <table className="ssh-keys-table">
            <thead>
              <tr>
                <th>Key ID</th>
                <th>Description</th>
                <th>Fingerprint</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.key_id}>
                  <td className="mono">{key.key_id}</td>
                  <td>{key.description || '-'}</td>
                  <td className="mono ssh-fingerprint">{key.fingerprint || '-'}</td>
                  <td>{key.created_at ? new Date(key.created_at).toLocaleDateString() : '-'}</td>
                  <td className="ssh-actions-cell">
                    <button
                      className="ssh-action-btn"
                      onClick={() => handleViewKey(key.key_id)}
                      title="View public key"
                    >
                      <Eye size={14} />
                    </button>
                    <button
                      className="ssh-action-btn ssh-action-danger"
                      onClick={() => setDeletingKey(key)}
                      title="Delete key"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {viewingKey && viewingPublicKey && (
            <div className="ssh-public-key-panel">
              <div className="ssh-public-key-panel-header">
                <span>Public Key ({viewingKey})</span>
                <button
                  className="ssh-copy-btn"
                  onClick={() => copyToClipboard(viewingPublicKey, viewingKey)}
                  title="Copy public key"
                >
                  {copiedId === viewingKey ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
              <div className="ssh-public-key-box">
                <code>{viewingPublicKey}</code>
              </div>
              <p className="ssh-generated-hint">
                Add this key as a deploy key with write access on your repository host.
              </p>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!deletingKey}
        onClose={() => setDeletingKey(null)}
        onConfirm={handleDelete}
        title="Delete SSH Key"
        message={`Are you sure you want to delete "${deletingKey?.description || deletingKey?.key_id}"? This cannot be undone.`}
        confirmText="Delete"
        variant="danger"
        loading={deleteLoading}
      />
    </div>
  )
}

export default SSHKeysPage
