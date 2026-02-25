import { useState } from 'react'
import { GitBranch, ExternalLink, Trash2, Server, RefreshCw, Upload, Link } from 'lucide-react'
import Card, { CardBody } from '../common/Card'
import { getRepoStatus, syncRepo, pushRepo, cloneRepo } from '../../api/sshKeys'
import { useToast } from '../../hooks/useToast'
import './Projects.css'

function LinkedRepoStatus({ projectId, repo }) {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [pushing, setPushing] = useState(false)
  const [cloning, setCloning] = useState(false)

  const loadStatus = async () => {
    setLoading(true)
    try {
      const data = await getRepoStatus(projectId, repo.repo_id)
      setStatus(data)
    } catch (err) {
      toast.error('Failed to load repo status')
    } finally {
      setLoading(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await syncRepo(projectId, repo.repo_id)
      if (result.success) {
        toast.success('Sync completed')
        loadStatus()
      } else {
        toast.error(result.message || 'Sync failed')
      }
    } catch (err) {
      toast.error(err.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const handlePush = async () => {
    setPushing(true)
    try {
      const result = await pushRepo(projectId, repo.repo_id, repo.default_branch)
      if (result.success) {
        toast.success('Push completed')
        loadStatus()
      } else {
        toast.error(result.message || 'Push failed')
      }
    } catch (err) {
      toast.error(err.message || 'Push failed')
    } finally {
      setPushing(false)
    }
  }

  const handleClone = async () => {
    setCloning(true)
    try {
      const result = await cloneRepo(projectId, repo.repo_id)
      if (result.success) {
        toast.success('Clone completed')
        loadStatus()
      } else {
        toast.error(result.message || 'Clone failed')
      }
    } catch (err) {
      toast.error(err.message || 'Clone failed')
    } finally {
      setCloning(false)
    }
  }

  const getStatusIndicator = () => {
    if (!status) return null
    const { clone_status } = status
    if (clone_status === 'cloned') {
      return <span className="repo-sync-badge synced">Cloned</span>
    }
    if (clone_status === 'cloning') {
      return <span className="repo-sync-badge syncing">Cloning...</span>
    }
    if (clone_status === 'error') {
      return <span className="repo-sync-badge error">Error</span>
    }
    return <span className="repo-sync-badge not-cloned">Not cloned</span>
  }

  return (
    <div className="linked-repo-status">
      <div className="linked-repo-info">
        <span className="meta-item">
          <span className="meta-label">Upstream:</span>
          <span className="mono" style={{ fontSize: 'var(--font-size-xs)' }}>{repo.url}</span>
        </span>
        {status && status.last_sync && (
          <span className="meta-item">
            <span className="meta-label">Last sync:</span>
            <span>{new Date(status.last_sync).toLocaleString()}</span>
          </span>
        )}
        {getStatusIndicator()}
      </div>
      <div className="linked-repo-actions">
        {!status && (
          <button
            className="repo-action-btn"
            onClick={loadStatus}
            disabled={loading}
            title="Check status"
          >
            <RefreshCw size={12} className={loading ? 'spinning' : ''} />
            <span>{loading ? 'Checking...' : 'Status'}</span>
          </button>
        )}
        {status && status.clone_status === 'not_cloned' && (
          <button
            className="repo-action-btn"
            onClick={handleClone}
            disabled={cloning}
            title="Clone repository"
          >
            <Link size={12} />
            <span>{cloning ? 'Cloning...' : 'Clone'}</span>
          </button>
        )}
        {status && status.clone_status === 'cloned' && (
          <>
            <button
              className="repo-action-btn"
              onClick={handleSync}
              disabled={syncing}
              title="Pull from upstream"
            >
              <RefreshCw size={12} className={syncing ? 'spinning' : ''} />
              <span>{syncing ? 'Syncing...' : 'Sync Now'}</span>
            </button>
            <button
              className="repo-action-btn"
              onClick={handlePush}
              disabled={pushing}
              title="Push to upstream"
            >
              <Upload size={12} />
              <span>{pushing ? 'Pushing...' : 'Push to Origin'}</span>
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function RepoList({ repos, onRemove, projectId }) {
  if (!repos || repos.length === 0) {
    return (
      <div className="empty-repos">
        <p>No repositories added to this project</p>
      </div>
    )
  }

  return (
    <div className="repo-list">
      {repos.map(repo => (
        <Card key={repo.repo_id} className="repo-card">
          <CardBody>
            <div className="repo-header">
              <GitBranch size={14} />
              <span className="repo-name">{repo.name}</span>
              {repo.is_internal && (
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--accent-primary)',
                  background: 'var(--bg-tertiary)',
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-sm)',
                  marginLeft: 'var(--space-xs)'
                }}>
                  <Server size={10} />
                  Internal
                </span>
              )}
              {!repo.is_internal && (
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-tertiary)',
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-sm)',
                  marginLeft: 'var(--space-xs)'
                }}>
                  <ExternalLink size={10} />
                  Linked
                </span>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: 'auto' }}>
                {!repo.is_internal && (
                  <a
                    href={repo.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="repo-link"
                    onClick={e => e.stopPropagation()}
                  >
                    <ExternalLink size={12} />
                  </a>
                )}
                {onRemove && (
                  <button
                    onClick={() => onRemove(repo)}
                    className="repo-remove-btn"
                    title="Remove repository"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
            <div className="repo-meta">
              <span className="meta-item">
                <span className="meta-label">Branch:</span>
                <span className="mono">{repo.default_branch}</span>
              </span>
              {repo.is_internal && (
                <span className="meta-item">
                  <span className="meta-label">URL:</span>
                  <span className="mono" style={{ fontSize: 'var(--font-size-xs)' }}>{repo.url}</span>
                </span>
              )}
              {repo.ssh_key_id && (
                <span className="meta-item">
                  <span className="meta-label">SSH Key:</span>
                  <span className="mono">{repo.ssh_key_id}</span>
                </span>
              )}
            </div>
            {!repo.is_internal && projectId && (
              <LinkedRepoStatus projectId={projectId} repo={repo} />
            )}
          </CardBody>
        </Card>
      ))}
    </div>
  )
}

export default RepoList
