import { GitBranch, ExternalLink, Trash2, Server } from 'lucide-react'
import Card, { CardBody } from '../common/Card'
import './Projects.css'

function RepoList({ repos, onRemove }) {
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
            </div>
          </CardBody>
        </Card>
      ))}
    </div>
  )
}

export default RepoList
