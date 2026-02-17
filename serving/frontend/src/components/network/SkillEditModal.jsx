import { useState, useEffect, useCallback } from 'react'
import { X, Eye, Edit2, Trash2 } from 'lucide-react'
import Modal from '../common/Modal'
import { getSkill, updateSkill, deleteSkill, getSkills, getAllTags } from '../../api/skills'
import '../common/Modal.css'
import './SkillCreateModal.css'

function SkillEditModal({ isOpen, onClose, skillId, onUpdated, onDeleted }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    instructions: '',
    tags: [],
    dependencies: [],
    specialized_tools: [],
    version: '1.0.0',
    changelog: ''
  })
  const [originalSkill, setOriginalSkill] = useState(null)
  const [tagInput, setTagInput] = useState('')
  const [toolInput, setToolInput] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [existingSkills, setExistingSkills] = useState([])
  const [existingTags, setExistingTags] = useState([])
  const [filteredTags, setFilteredTags] = useState([])
  const [showTagSuggestions, setShowTagSuggestions] = useState(false)

  useEffect(() => {
    if (isOpen && skillId) {
      setLoading(true)
      setError(null)
      setShowDeleteConfirm(false)

      Promise.all([
        getSkill(skillId),
        getSkills(),
        getAllTags()
      ])
        .then(([skill, skills, tags]) => {
          setOriginalSkill(skill)
          setFormData({
            name: skill.name || '',
            description: skill.description || '',
            instructions: skill.instructions || '',
            tags: skill.tags || [],
            dependencies: skill.dependencies || [],
            specialized_tools: skill.specialized_tools || [],
            version: skill.version || '1.0.0',
            changelog: ''
          })
          // Filter out current skill from dependencies list
          setExistingSkills(skills.filter(s => s.id !== skillId))
          setExistingTags(tags)
          setLoading(false)
        })
        .catch(err => {
          setError(err.message)
          setLoading(false)
        })
    }
  }, [isOpen, skillId])

  useEffect(() => {
    if (tagInput.trim()) {
      const filtered = existingTags.filter(
        tag => tag.toLowerCase().includes(tagInput.toLowerCase()) && !formData.tags.includes(tag)
      )
      setFilteredTags(filtered)
      setShowTagSuggestions(filtered.length > 0)
    } else {
      setFilteredTags([])
      setShowTagSuggestions(false)
    }
  }, [tagInput, existingTags, formData.tags])

  const handleChange = useCallback((e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setError(null)
  }, [])

  const handleAddTag = useCallback((tagToAdd = null) => {
    const tag = (tagToAdd || tagInput).trim().toLowerCase()
    if (tag && !formData.tags.includes(tag)) {
      setFormData(prev => ({ ...prev, tags: [...prev.tags, tag] }))
    }
    setTagInput('')
    setShowTagSuggestions(false)
  }, [tagInput, formData.tags])

  const handleRemoveTag = useCallback((tag) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags.filter(t => t !== tag)
    }))
  }, [])

  const handleTagKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddTag()
    }
  }, [handleAddTag])

  const handleAddTool = useCallback(() => {
    const tool = toolInput.trim()
    if (tool && !formData.specialized_tools.includes(tool)) {
      setFormData(prev => ({
        ...prev,
        specialized_tools: [...prev.specialized_tools, tool]
      }))
    }
    setToolInput('')
  }, [toolInput, formData.specialized_tools])

  const handleRemoveTool = useCallback((tool) => {
    setFormData(prev => ({
      ...prev,
      specialized_tools: prev.specialized_tools.filter(t => t !== tool)
    }))
  }, [])

  const handleToolKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddTool()
    }
  }, [handleAddTool])

  const handleToggleDependency = useCallback((skillDependencyId) => {
    setFormData(prev => ({
      ...prev,
      dependencies: prev.dependencies.includes(skillDependencyId)
        ? prev.dependencies.filter(id => id !== skillDependencyId)
        : [...prev.dependencies, skillDependencyId]
    }))
  }, [])

  const validate = useCallback(() => {
    if (!formData.name.trim()) {
      return 'Name is required'
    }
    if (!formData.description.trim()) {
      return 'Description is required'
    }
    if (!formData.instructions.trim()) {
      return 'Instructions are required'
    }
    return null
  }, [formData])

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault()

    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      // Build update payload - only include changed fields
      const updateData = {}
      if (formData.name !== originalSkill.name) updateData.name = formData.name
      if (formData.description !== originalSkill.description) updateData.description = formData.description
      if (formData.instructions !== originalSkill.instructions) updateData.instructions = formData.instructions
      if (formData.version !== originalSkill.version) updateData.version = formData.version
      if (JSON.stringify(formData.tags) !== JSON.stringify(originalSkill.tags || [])) updateData.tags = formData.tags
      if (JSON.stringify(formData.specialized_tools) !== JSON.stringify(originalSkill.specialized_tools || [])) {
        updateData.specialized_tools = formData.specialized_tools
      }
      if (JSON.stringify(formData.dependencies) !== JSON.stringify(originalSkill.dependencies || [])) {
        updateData.dependencies = formData.dependencies
      }
      if (formData.changelog.trim()) {
        updateData.changelog = formData.changelog
      }

      const skill = await updateSkill(skillId, updateData)
      onUpdated?.(skill)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }, [formData, originalSkill, skillId, validate, onUpdated, onClose])

  const handleDelete = useCallback(async () => {
    setDeleting(true)
    setError(null)

    try {
      await deleteSkill(skillId)
      onDeleted?.(skillId)
      onClose()
    } catch (err) {
      setError(err.message)
      setDeleting(false)
      setShowDeleteConfirm(false)
    }
  }, [skillId, onDeleted, onClose])

  if (!isOpen) return null

  const isSystem = originalSkill?.author === 'system'
  const canEdit = !isSystem
  const canDelete = !isSystem

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Edit Skill" width="700px">
      {loading ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading...
        </div>
      ) : error && !originalSkill ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--status-offline)' }}>
          {error}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="skill-create-form">
          {isSystem && (
            <div className="form-error" style={{ background: 'rgba(234, 179, 8, 0.1)', borderColor: 'var(--status-degraded)', color: 'var(--status-degraded)' }}>
              System skills are read-only and cannot be modified.
            </div>
          )}

          {error && (
            <div className="form-error">
              {error}
            </div>
          )}

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">
                Skill ID
              </label>
              <input
                type="text"
                className="form-input mono"
                value={skillId}
                disabled
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="skill-version">
                Version
              </label>
              <input
                id="skill-version"
                name="version"
                type="text"
                className="form-input"
                value={formData.version}
                onChange={handleChange}
                placeholder="1.0.0"
                disabled={submitting || !canEdit}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="skill-name">
              Name <span className="required">*</span>
            </label>
            <input
              id="skill-name"
              name="name"
              type="text"
              className="form-input"
              value={formData.name}
              onChange={handleChange}
              placeholder="My Skill"
              disabled={submitting || !canEdit}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="skill-description">
              Description <span className="required">*</span>
            </label>
            <textarea
              id="skill-description"
              name="description"
              className="form-textarea"
              value={formData.description}
              onChange={handleChange}
              placeholder="What this skill does..."
              disabled={submitting || !canEdit}
              rows={2}
            />
          </div>

          <div className="form-group">
            <div className="form-label-row">
              <label className="form-label" htmlFor="skill-instructions">
                Instructions <span className="required">*</span>
              </label>
              <button
                type="button"
                className="preview-toggle"
                onClick={() => setShowPreview(!showPreview)}
              >
                {showPreview ? <Edit2 size={14} /> : <Eye size={14} />}
                {showPreview ? 'Edit' : 'Preview'}
              </button>
            </div>
            {showPreview ? (
              <div className="instructions-preview">
                {formData.instructions || 'No instructions yet...'}
              </div>
            ) : (
              <textarea
                id="skill-instructions"
                name="instructions"
                className="form-textarea form-textarea-large mono"
                value={formData.instructions}
                onChange={handleChange}
                placeholder="# Skill Instructions&#10;&#10;Write markdown instructions for Claude..."
                disabled={submitting || !canEdit}
                rows={8}
              />
            )}
            <span className="form-hint">Markdown supported</span>
          </div>

          <div className="form-group">
            <label className="form-label">Tags</label>
            <div className="tag-input-container">
              <div className="tags-list">
                {formData.tags.map(tag => (
                  <span key={tag} className="tag-chip">
                    {tag}
                    {canEdit && (
                      <button
                        type="button"
                        className="tag-remove"
                        onClick={() => handleRemoveTag(tag)}
                        disabled={submitting}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </span>
                ))}
              </div>
              {canEdit && (
                <div className="tag-input-wrapper">
                  <input
                    type="text"
                    className="form-input"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={handleTagKeyDown}
                    onFocus={() => tagInput && setShowTagSuggestions(filteredTags.length > 0)}
                    onBlur={() => setTimeout(() => setShowTagSuggestions(false), 150)}
                    placeholder="Add tag and press Enter"
                    disabled={submitting}
                  />
                  {showTagSuggestions && (
                    <div className="tag-suggestions">
                      {filteredTags.slice(0, 5).map(tag => (
                        <button
                          key={tag}
                          type="button"
                          className="tag-suggestion"
                          onClick={() => handleAddTag(tag)}
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Specialized Tools</label>
            <div className="tag-input-container">
              <div className="tags-list">
                {formData.specialized_tools.map(tool => (
                  <span key={tool} className="tag-chip tag-chip-tool">
                    {tool}
                    {canEdit && (
                      <button
                        type="button"
                        className="tag-remove"
                        onClick={() => handleRemoveTool(tool)}
                        disabled={submitting}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </span>
                ))}
              </div>
              {canEdit && (
                <input
                  type="text"
                  className="form-input mono"
                  value={toolInput}
                  onChange={(e) => setToolInput(e.target.value)}
                  onKeyDown={handleToolKeyDown}
                  placeholder="Add tool ID and press Enter"
                  disabled={submitting}
                />
              )}
            </div>
            <span className="form-hint">Tool IDs that this skill grants access to</span>
          </div>

          <div className="form-group">
            <label className="form-label">Dependencies</label>
            <div className="dependency-list">
              {existingSkills.length === 0 ? (
                <span className="form-hint">No other skills available</span>
              ) : (
                existingSkills.map(skill => (
                  <label key={skill.id} className="dependency-item">
                    <input
                      type="checkbox"
                      checked={formData.dependencies.includes(skill.id)}
                      onChange={() => handleToggleDependency(skill.id)}
                      disabled={submitting || !canEdit}
                    />
                    <span className="dependency-name">{skill.name}</span>
                    <span className="dependency-id">{skill.id}</span>
                  </label>
                ))
              )}
            </div>
            <span className="form-hint">Skills that are automatically included when this skill is selected</span>
          </div>

          {canEdit && (
            <div className="form-group">
              <label className="form-label" htmlFor="skill-changelog">
                Change Notes (optional)
              </label>
              <textarea
                id="skill-changelog"
                name="changelog"
                className="form-textarea"
                value={formData.changelog}
                onChange={handleChange}
                placeholder="Describe what changed in this update..."
                disabled={submitting}
                rows={2}
              />
              <span className="form-hint">Will be recorded in version history</span>
            </div>
          )}

          {showDeleteConfirm ? (
            <div className="form-error" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>Are you sure you want to delete this skill?</span>
              <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          ) : (
            <div className="form-actions" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div>
                {canDelete && (
                  <button
                    type="button"
                    className="btn btn-danger-outline"
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={submitting}
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </button>
                {canEdit && (
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={submitting}
                  >
                    {submitting ? 'Saving...' : 'Save Changes'}
                  </button>
                )}
              </div>
            </div>
          )}
        </form>
      )}
    </Modal>
  )
}

export default SkillEditModal
