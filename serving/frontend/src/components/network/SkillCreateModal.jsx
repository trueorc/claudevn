import { useState, useEffect, useCallback } from 'react'
import { X, Eye, Edit2 } from 'lucide-react'
import Modal from '../common/Modal'
import { createSkill, getSkills, getAllTags } from '../../api/skills'
import '../common/Modal.css'
import './SkillCreateModal.css'

const ID_PATTERN = /^[a-z][a-z0-9-]*$/

function SkillCreateModal({ isOpen, onClose, onCreated }) {
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    description: '',
    instructions: '',
    tags: [],
    dependencies: [],
    specialized_tools: [],
    version: '1.0.0'
  })
  const [tagInput, setTagInput] = useState('')
  const [toolInput, setToolInput] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [existingSkills, setExistingSkills] = useState([])
  const [existingTags, setExistingTags] = useState([])
  const [filteredTags, setFilteredTags] = useState([])
  const [showTagSuggestions, setShowTagSuggestions] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setFormData({
        id: '',
        name: '',
        description: '',
        instructions: '',
        tags: [],
        dependencies: [],
        specialized_tools: [],
        version: '1.0.0'
      })
      setTagInput('')
      setToolInput('')
      setShowPreview(false)
      setError(null)

      Promise.all([getSkills(), getAllTags()])
        .then(([skills, tags]) => {
          setExistingSkills(skills)
          setExistingTags(tags)
        })
        .catch(() => {})
    }
  }, [isOpen])

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

  const handleToggleDependency = useCallback((skillId) => {
    setFormData(prev => ({
      ...prev,
      dependencies: prev.dependencies.includes(skillId)
        ? prev.dependencies.filter(id => id !== skillId)
        : [...prev.dependencies, skillId]
    }))
  }, [])

  const validate = useCallback(() => {
    if (!formData.id.trim()) {
      return 'Skill ID is required'
    }
    if (!ID_PATTERN.test(formData.id)) {
      return 'Skill ID must start with a letter and contain only lowercase letters, numbers, and hyphens'
    }
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
      const skill = await createSkill(formData)
      onCreated?.(skill)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }, [formData, validate, onCreated, onClose])

  if (!isOpen) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create Skill" width="700px">
      <form onSubmit={handleSubmit} className="skill-create-form">
        {error && (
          <div className="form-error">
            {error}
          </div>
        )}

        <div className="form-row">
          <div className="form-group">
            <label className="form-label" htmlFor="skill-id">
              Skill ID <span className="required">*</span>
            </label>
            <input
              id="skill-id"
              name="id"
              type="text"
              className="form-input mono"
              value={formData.id}
              onChange={handleChange}
              placeholder="my-skill-id"
              disabled={submitting}
            />
            <span className="form-hint">Lowercase letters, numbers, and hyphens only</span>
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
              disabled={submitting}
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
            disabled={submitting}
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
            disabled={submitting}
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
              disabled={submitting}
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
                  <button
                    type="button"
                    className="tag-remove"
                    onClick={() => handleRemoveTag(tag)}
                    disabled={submitting}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
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
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Specialized Tools</label>
          <div className="tag-input-container">
            <div className="tags-list">
              {formData.specialized_tools.map(tool => (
                <span key={tool} className="tag-chip tag-chip-tool">
                  {tool}
                  <button
                    type="button"
                    className="tag-remove"
                    onClick={() => handleRemoveTool(tool)}
                    disabled={submitting}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
            <input
              type="text"
              className="form-input mono"
              value={toolInput}
              onChange={(e) => setToolInput(e.target.value)}
              onKeyDown={handleToolKeyDown}
              placeholder="Add tool ID and press Enter"
              disabled={submitting}
            />
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
                    disabled={submitting}
                  />
                  <span className="dependency-name">{skill.name}</span>
                  <span className="dependency-id">{skill.id}</span>
                </label>
              ))
            )}
          </div>
          <span className="form-hint">Skills that are automatically included when this skill is selected</span>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
          >
            {submitting ? 'Creating...' : 'Create Skill'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default SkillCreateModal
