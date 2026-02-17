import { useState, useEffect } from 'react'
import Modal from '../common/Modal'
import { createIssue, updateIssue, getGoals, getAllIssues, getReleases } from '../../api/workmap'
import './IssueFormModal.css'

const issueTypes = [
  { value: 'feature', label: 'Feature' },
  { value: 'bug', label: 'Bug' },
  { value: 'refactor', label: 'Refactor' },
  { value: 'docs', label: 'Documentation' },
  { value: 'test', label: 'Test' }
]

const issueAreas = [
  { value: 'api', label: 'API' },
  { value: 'database', label: 'Database' },
  { value: 'frontend', label: 'Frontend' },
  { value: 'infra', label: 'Infrastructure' },
  { value: 'other', label: 'Other' }
]

const issuePriorities = [
  { value: 'P0', label: 'P0 - Critical' },
  { value: 'P1', label: 'P1 - High' },
  { value: 'P2', label: 'P2 - Medium' },
  { value: 'P3', label: 'P3 - Low' }
]

function IssueFormModal({ isOpen, onClose, issue, onSuccess, projectId }) {
  const isEditing = Boolean(issue)
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    issue_type: 'feature',
    area: 'other',
    priority: 'P2',
    required_skills: [],
    depends_on: [],
    goal_id: '',
    release_id: ''
  })
  const [goals, setGoals] = useState([])
  const [releases, setReleases] = useState([])
  const [availableIssues, setAvailableIssues] = useState([])
  const [skillInput, setSkillInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (isOpen) {
      loadFormData()
      if (issue) {
        setFormData({
          title: issue.title || '',
          description: issue.description || '',
          issue_type: issue.issue_type || 'feature',
          area: issue.area || 'other',
          priority: issue.priority || 'P2',
          required_skills: issue.required_skills || [],
          depends_on: issue.depends_on || [],
          goal_id: issue.goal_id || '',
          release_id: issue.release_id || ''
        })
      } else {
        setFormData({
          title: '',
          description: '',
          issue_type: 'feature',
          area: 'other',
          priority: 'P2',
          required_skills: [],
          depends_on: [],
          goal_id: '',
          release_id: ''
        })
      }
      setSkillInput('')
      setError(null)
    }
  }, [isOpen, issue])

  const loadFormData = async () => {
    try {
      const [goalsData, issuesData, releasesData] = await Promise.all([
        getGoals(),
        getAllIssues(),
        getReleases()
      ])
      setGoals(goalsData || [])
      setAvailableIssues(issuesData?.items || [])
      setReleases(releasesData?.items || [])
    } catch (err) {
      console.error('Failed to load form data:', err)
    }
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleAddSkill = () => {
    const skill = skillInput.trim()
    if (skill && !formData.required_skills.includes(skill)) {
      setFormData(prev => ({
        ...prev,
        required_skills: [...prev.required_skills, skill]
      }))
      setSkillInput('')
    }
  }

  const handleRemoveSkill = (skill) => {
    setFormData(prev => ({
      ...prev,
      required_skills: prev.required_skills.filter(s => s !== skill)
    }))
  }

  const handleSkillKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddSkill()
    }
  }

  const handleDependencyChange = (issueId) => {
    setFormData(prev => {
      const currentDeps = prev.depends_on
      if (currentDeps.includes(issueId)) {
        return { ...prev, depends_on: currentDeps.filter(id => id !== issueId) }
      } else {
        return { ...prev, depends_on: [...currentDeps, issueId] }
      }
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const payload = {
        title: formData.title,
        description: formData.description,
        issue_type: formData.issue_type,
        area: formData.area,
        priority: formData.priority,
        required_skills: formData.required_skills,
        depends_on: formData.depends_on
      }

      if (formData.goal_id) {
        payload.goal_id = formData.goal_id
      }

      if (formData.release_id) {
        payload.release_id = formData.release_id
      }

      if (!isEditing && projectId) {
        payload.project_id = projectId
      }

      if (isEditing) {
        await updateIssue(issue.issue_id, payload)
      } else {
        await createIssue(payload)
      }

      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to save issue')
    } finally {
      setLoading(false)
    }
  }

  // Filter out the current issue from dependencies when editing
  const dependencyOptions = availableIssues.filter(
    i => !isEditing || i.issue_id !== issue?.issue_id
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Issue' : 'Create Issue'}
      width="560px"
    >
      <form onSubmit={handleSubmit} className="issue-form">
        {error && (
          <div className="form-error">{error}</div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="title">Title *</label>
          <input
            id="title"
            name="title"
            type="text"
            className="form-input"
            value={formData.title}
            onChange={handleChange}
            placeholder="Brief issue title"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="description">Description *</label>
          <textarea
            id="description"
            name="description"
            className="form-textarea"
            value={formData.description}
            onChange={handleChange}
            placeholder="Detailed description of the issue"
            rows={4}
            required
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="form-label" htmlFor="issue_type">Type</label>
            <select
              id="issue_type"
              name="issue_type"
              className="form-select"
              value={formData.issue_type}
              onChange={handleChange}
            >
              {issueTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="area">Area</label>
            <select
              id="area"
              name="area"
              className="form-select"
              value={formData.area}
              onChange={handleChange}
            >
              {issueAreas.map(area => (
                <option key={area.value} value={area.value}>{area.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="priority">Priority</label>
            <select
              id="priority"
              name="priority"
              className="form-select"
              value={formData.priority}
              onChange={handleChange}
            >
              {issuePriorities.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="goal_id">Link to Goal</label>
          <select
            id="goal_id"
            name="goal_id"
            className="form-select"
            value={formData.goal_id}
            onChange={handleChange}
          >
            <option value="">No Goal</option>
            {goals.map(goal => (
              <option key={goal.goal_id} value={goal.goal_id}>
                {goal.title}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="release_id">Target Release</label>
          <select
            id="release_id"
            name="release_id"
            className="form-select"
            value={formData.release_id}
            onChange={handleChange}
          >
            <option value="">Unscheduled</option>
            {releases.map(release => (
              <option key={release.release_id} value={release.release_id}>
                {release.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Required Skills</label>
          <div className="skill-input-row">
            <input
              type="text"
              className="form-input"
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={handleSkillKeyDown}
              placeholder="Enter skill name"
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleAddSkill}
              disabled={!skillInput.trim()}
            >
              Add
            </button>
          </div>
          {formData.required_skills.length > 0 && (
            <div className="skill-tags">
              {formData.required_skills.map(skill => (
                <span key={skill} className="skill-tag">
                  {skill}
                  <button
                    type="button"
                    className="skill-tag-remove"
                    onClick={() => handleRemoveSkill(skill)}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="form-group">
          <label className="form-label">Dependencies</label>
          <div className="dependency-list">
            {dependencyOptions.length > 0 ? (
              dependencyOptions.slice(0, 20).map(dep => (
                <label key={dep.issue_id} className="dependency-option">
                  <input
                    type="checkbox"
                    checked={formData.depends_on.includes(dep.issue_id)}
                    onChange={() => handleDependencyChange(dep.issue_id)}
                  />
                  <span className="dependency-id">#{dep.issue_id.slice(0, 8)}</span>
                  <span className="dependency-title">{dep.title}</span>
                </label>
              ))
            ) : (
              <span className="no-dependencies">No other issues available</span>
            )}
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Saving...' : isEditing ? 'Save Changes' : 'Create Issue'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default IssueFormModal
