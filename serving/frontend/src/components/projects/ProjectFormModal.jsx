import { useState, useEffect, useRef } from 'react'
import { X, FolderGit2, Code, Database, Server, Globe, Folder, Box, Layers, Cpu, Cloud, Shield, ChevronDown, ChevronRight, Plus, GitBranch, Trash2 } from 'lucide-react'
import Modal from '../common/Modal'
import { createProject, updateProject } from '../../api/projects'
import { useSSHKeys } from '../../hooks/useSSHKeys'
import '../common/Modal.css'
import './Projects.css'

const ICONS = [
  { name: 'folder', Icon: FolderGit2, label: 'Folder' },
  { name: 'code', Icon: Code, label: 'Code' },
  { name: 'database', Icon: Database, label: 'Database' },
  { name: 'server', Icon: Server, label: 'Server' },
  { name: 'globe', Icon: Globe, label: 'Web' },
  { name: 'folder-simple', Icon: Folder, label: 'Simple Folder' },
  { name: 'box', Icon: Box, label: 'Box' },
  { name: 'layers', Icon: Layers, label: 'Layers' },
  { name: 'cpu', Icon: Cpu, label: 'CPU' },
  { name: 'cloud', Icon: Cloud, label: 'Cloud' },
  { name: 'shield', Icon: Shield, label: 'Security' },
]

const COLORS = [
  '#6366f1', // indigo (default primary)
  '#8b5cf6', // violet
  '#a855f7', // purple
  '#d946ef', // fuchsia
  '#ec4899', // pink
  '#f43f5e', // rose
  '#ef4444', // red
  '#f97316', // orange
  '#f59e0b', // amber
  '#eab308', // yellow
  '#84cc16', // lime
  '#22c55e', // green
  '#10b981', // emerald
  '#14b8a6', // teal
  '#06b6d4', // cyan
  '#0ea5e9', // sky
  '#3b82f6', // blue
  '#64748b', // slate
]

function IconPicker({ selectedIcon, onSelect }) {
  return (
    <div className="icon-picker">
      {ICONS.map(({ name, Icon, label }) => (
        <button
          key={name}
          type="button"
          className={`icon-picker-btn ${selectedIcon === name ? 'selected' : ''}`}
          onClick={() => onSelect(selectedIcon === name ? null : name)}
          title={label}
        >
          <Icon size={18} />
        </button>
      ))}
    </div>
  )
}

function ColorPicker({ selectedColor, onSelect }) {
  return (
    <div className="color-picker">
      {COLORS.map((color) => (
        <button
          key={color}
          type="button"
          className={`color-picker-btn ${selectedColor === color ? 'selected' : ''}`}
          style={{ backgroundColor: color }}
          onClick={() => onSelect(selectedColor === color ? null : color)}
          title={color}
        />
      ))}
    </div>
  )
}

function LabelsInput({ labels, onChange }) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef(null)

  const addLabel = (label) => {
    const trimmed = label.trim().toLowerCase()
    if (trimmed && !labels.includes(trimmed)) {
      onChange([...labels, trimmed])
    }
    setInputValue('')
  }

  const removeLabel = (labelToRemove) => {
    onChange(labels.filter((l) => l !== labelToRemove))
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addLabel(inputValue)
    } else if (e.key === 'Backspace' && !inputValue && labels.length > 0) {
      removeLabel(labels[labels.length - 1])
    }
  }

  const handleContainerClick = () => {
    inputRef.current?.focus()
  }

  return (
    <div className="labels-input-container" onClick={handleContainerClick}>
      {labels.map((label) => (
        <span key={label} className="label-tag">
          {label}
          <button
            type="button"
            className="label-tag-remove"
            onClick={(e) => {
              e.stopPropagation()
              removeLabel(label)
            }}
          >
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        className="labels-input"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => inputValue && addLabel(inputValue)}
        placeholder={labels.length === 0 ? 'Add labels...' : ''}
      />
    </div>
  )
}

function InlineRepoForm({ onAdd }) {
  const [mode, setMode] = useState('create')
  const [repoName, setRepoName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [defaultBranch, setDefaultBranch] = useState('main')
  const [sshKeyId, setSshKeyId] = useState('')
  const [formError, setFormError] = useState(null)

  const { keys, loading: keysLoading } = useSSHKeys()

  const handleAdd = () => {
    if (!repoName.trim()) {
      setFormError('Repository name is required')
      return
    }
    if (mode === 'link' && !repoUrl.trim()) {
      setFormError('Repository URL is required')
      return
    }

    onAdd({
      mode,
      name: repoName.trim(),
      url: mode === 'link' ? repoUrl.trim() : null,
      default_branch: defaultBranch.trim() || 'main',
      ssh_key_id: mode === 'link' && sshKeyId ? sshKeyId : null,
    })

    setRepoName('')
    setRepoUrl('')
    setDefaultBranch('main')
    setSshKeyId('')
    setFormError(null)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAdd()
    }
  }

  const tabStyle = (active) => ({
    padding: 'var(--space-xs) var(--space-sm)',
    border: 'none',
    borderBottom: active ? '2px solid var(--accent-primary)' : '2px solid transparent',
    background: 'none',
    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
    cursor: 'pointer',
    fontWeight: active ? '600' : '400',
    fontSize: 'var(--font-size-xs)',
  })

  return (
    <div className="inline-repo-form">
      <div className="inline-repo-tabs">
        <button
          type="button"
          style={tabStyle(mode === 'create')}
          onClick={() => { setMode('create'); setFormError(null) }}
        >
          Create New
        </button>
        <button
          type="button"
          style={tabStyle(mode === 'link')}
          onClick={() => { setMode('link'); setFormError(null) }}
        >
          Link External
        </button>
      </div>

      <div className="inline-repo-fields">
        <input
          type="text"
          className="form-input"
          value={repoName}
          onChange={(e) => setRepoName(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Repository name"
        />

        {mode === 'link' && (
          <input
            type="text"
            className="form-input"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="https://github.com/org/repo.git"
          />
        )}

        <input
          type="text"
          className="form-input"
          value={defaultBranch}
          onChange={(e) => setDefaultBranch(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Default branch (main)"
        />

        {mode === 'link' && (
          <select
            className="form-input"
            value={sshKeyId}
            onChange={(e) => setSshKeyId(e.target.value)}
          >
            <option value="">SSH Key: None (no authentication)</option>
            {keysLoading && <option disabled>Loading keys...</option>}
            {keys.map((key) => (
              <option key={key.key_id} value={key.key_id}>
                {key.key_id}{key.description ? ` - ${key.description}` : ''}
              </option>
            ))}
          </select>
        )}
      </div>

      {formError && (
        <div style={{ color: 'var(--status-offline)', fontSize: 'var(--font-size-xs)', marginTop: 'var(--space-xs)' }}>
          {formError}
        </div>
      )}

      <button type="button" className="btn btn-secondary inline-repo-add-btn" onClick={handleAdd}>
        <Plus size={14} />
        Add to list
      </button>
    </div>
  )
}

function PendingRepoList({ repos, onRemove }) {
  if (repos.length === 0) return null

  return (
    <div className="pending-repo-list">
      {repos.map((repo, index) => (
        <div key={index} className="pending-repo-item">
          <GitBranch size={14} className="pending-repo-icon" />
          <div className="pending-repo-info">
            <span className="pending-repo-name">{repo.name}</span>
            <span className="pending-repo-meta">
              {repo.mode === 'create' ? 'Internal' : 'External'} · {repo.default_branch}
            </span>
          </div>
          <button
            type="button"
            className="repo-remove-btn"
            onClick={() => onRemove(index)}
            title="Remove"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

function ProjectFormModal({ isOpen, onClose, onSuccess, project = null }) {
  const isEditing = !!project
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState(null)
  const [iconColor, setIconColor] = useState(null)
  const [labels, setLabels] = useState([])
  const [pendingRepos, setPendingRepos] = useState([])
  const [repoSectionOpen, setRepoSectionOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (isOpen) {
      if (project) {
        setName(project.name || '')
        setDescription(project.description || '')
        setIcon(project.icon || null)
        setIconColor(project.icon_color || null)
        setLabels(project.labels || [])
      } else {
        setName('')
        setDescription('')
        setIcon(null)
        setIconColor(null)
        setLabels([])
        setPendingRepos([])
        setRepoSectionOpen(false)
      }
      setError(null)
    }
  }, [isOpen, project])

  const addPendingRepo = (repo) => {
    setPendingRepos((prev) => [...prev, repo])
  }

  const removePendingRepo = (index) => {
    setPendingRepos((prev) => prev.filter((_, i) => i !== index))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!name.trim()) {
      setError('Project name is required')
      return
    }

    setSaving(true)
    setError(null)

    try {
      const data = {
        name: name.trim(),
        description: description.trim() || '',
        icon: icon,
        icon_color: iconColor,
        labels: labels,
      }

      if (isEditing) {
        await updateProject(project.project_id, data)
      } else {
        // Send repos atomically with project creation
        const createData = {
          ...data,
          repos: pendingRepos.map((repo) => ({
            mode: repo.mode,
            name: repo.name,
            url: repo.url,
            default_branch: repo.default_branch,
            ssh_key_id: repo.ssh_key_id,
          })),
        }

        const created = await createProject(createData)

        // Surface clone errors from repos that failed
        const repoErrors = (created.repos || [])
          .filter((r) => r.metadata?.clone_error)
          .map((r) => `${r.name}: ${r.metadata.clone_error}`)

        if (repoErrors.length > 0) {
          setError(`Project created, but some repos had clone errors:\n${repoErrors.join('\n')}`)
          setSaving(false)
          onSuccess()
          return
        }
      }

      onSuccess()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to save project')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Project' : 'New Project'}
      width="680px"
    >
      <form onSubmit={handleSubmit}>
        <div className="project-form-columns">
          <div className="project-form-left">
            <div className="form-group">
              <label className="form-label" htmlFor="project-name">
                Name
              </label>
              <input
                id="project-name"
                type="text"
                className="form-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Project"
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="project-description">
                Description
              </label>
              <textarea
                id="project-description"
                className="form-textarea"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description..."
              />
            </div>

            <div className="form-group">
              <label className="form-label">Labels</label>
              <LabelsInput labels={labels} onChange={setLabels} />
              <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-xs)' }}>
                Press Enter or comma to add a label
              </p>
            </div>
          </div>

          <div className="project-form-right">
            <div className="form-group">
              <label className="form-label">Icon</label>
              <IconPicker selectedIcon={icon} onSelect={setIcon} />
            </div>

            <div className="form-group">
              <label className="form-label">Icon Color</label>
              <ColorPicker selectedColor={iconColor} onSelect={setIconColor} />
            </div>
          </div>
        </div>

        {!isEditing && (
          <div className="form-group">
            <button
              type="button"
              className="repo-section-toggle"
              onClick={() => setRepoSectionOpen(!repoSectionOpen)}
            >
              {repoSectionOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span>Repositories</span>
              {pendingRepos.length > 0 && (
                <span className="repo-count-badge">{pendingRepos.length}</span>
              )}
            </button>

            {repoSectionOpen && (
              <div className="repo-section-content">
                <PendingRepoList repos={pendingRepos} onRemove={removePendingRepo} />
                <InlineRepoForm onAdd={addPendingRepo} />
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
            {saving ? 'Saving...' : isEditing ? 'Save Changes' : 'Create Project'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default ProjectFormModal
