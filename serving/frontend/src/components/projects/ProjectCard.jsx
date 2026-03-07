import { FolderGit2, GitBranch, Pencil, Trash2, CheckCircle2, Activity, Code, Database, Server, Globe, Folder, Box, Layers, Cpu, Cloud, Shield, ArrowRight } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../common/Card'
import { StatusBadge } from '../common/Badge'
import './Projects.css'

const ICON_MAP = {
  folder: FolderGit2,
  code: Code,
  database: Database,
  server: Server,
  globe: Globe,
  'folder-simple': Folder,
  box: Box,
  layers: Layers,
  cpu: Cpu,
  cloud: Cloud,
  shield: Shield,
}

function formatRelativeTime(dateString) {
  if (!dateString) return null

  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMinutes < 1) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}

function ActivityIndicator({ indicator }) {
  const colorMap = {
    green: 'var(--status-online)',
    yellow: 'var(--status-degraded)',
    red: 'var(--status-offline)',
    gray: 'var(--text-muted)'
  }

  return (
    <span
      className="activity-indicator"
      style={{ backgroundColor: colorMap[indicator] || colorMap.gray }}
      title={`Activity: ${indicator}`}
    />
  )
}

function ProjectIcon({ icon, iconColor, name, size = 'sm' }) {
  const IconComponent = icon ? ICON_MAP[icon] : null
  const fallbackLetter = name ? name.charAt(0).toUpperCase() : '?'
  const bgColor = iconColor || 'var(--primary)'
  const iconSize = size === 'lg' ? 24 : 16
  const containerSize = size === 'lg' ? 40 : 28

  return (
    <div
      className={`project-icon-container project-icon-${size}`}
      style={{
        backgroundColor: bgColor,
        width: containerSize,
        height: containerSize,
      }}
    >
      {IconComponent ? (
        <IconComponent size={iconSize} />
      ) : (
        <span className="project-icon-letter">{fallbackLetter}</span>
      )}
    </div>
  )
}

function ProjectLabels({ labels }) {
  if (!labels || labels.length === 0) return null

  return (
    <div className="project-labels">
      {labels.slice(0, 4).map((label, index) => (
        <span key={index} className="project-label">
          {label}
        </span>
      ))}
      {labels.length > 4 && (
        <span className="project-label project-label-more">+{labels.length - 4}</span>
      )}
    </div>
  )
}

function ProjectCard({ project, onClick, onEdit, onDelete, onSelectActive, isActive }) {
  const {
    name,
    description,
    status,
    repos,
    created_at,
    icon,
    icon_color,
    labels,
    activity_summary
  } = project

  const handleEdit = (e) => {
    e.stopPropagation()
    onEdit?.(project)
  }

  const handleDelete = (e) => {
    e.stopPropagation()
    onDelete?.(project)
  }

  const handleSelectActive = (e) => {
    e.stopPropagation()
    onSelectActive?.(project)
  }

  const lastActivityText = activity_summary?.last_activity_at
    ? formatRelativeTime(activity_summary.last_activity_at)
    : null

  return (
    <Card className="project-card" onClick={onClick}>
      <CardHeader>
        <div className="project-info">
          <ProjectIcon icon={icon} iconColor={icon_color} name={name} />
          <span className="project-name">{name}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusBadge status={status} />
          {onSelectActive && !isActive && (
            <button
              onClick={handleSelectActive}
              className="project-action-btn project-action-btn-select"
              title="Select as active project"
            >
              <ArrowRight size={14} />
              <span className="project-select-label">Select</span>
            </button>
          )}
          {isActive && (
            <span className="project-active-badge">Active</span>
          )}
          {onEdit && (
            <button
              onClick={handleEdit}
              className="project-action-btn"
              title="Edit project"
            >
              <Pencil size={14} />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              className="project-action-btn project-action-btn-danger"
              title="Delete project"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </CardHeader>
      <CardBody>
        {description && (
          <p className="project-description">{description}</p>
        )}
        <ProjectLabels labels={labels} />
        <div className="project-meta">
          <span className="meta-item">
            <GitBranch size={12} />
            <span>{repos?.length || 0} repos</span>
          </span>
          {activity_summary && (
            <>
              <span className="meta-item activity-item">
                <ActivityIndicator indicator={activity_summary.indicator} />
                <span>
                  {lastActivityText ? `Active ${lastActivityText}` : 'No activity'}
                </span>
              </span>
              {activity_summary.active_work_items > 0 && (
                <span className="meta-item">
                  <Activity size={12} />
                  <span>{activity_summary.active_work_items} active</span>
                </span>
              )}
              {activity_summary.completed_week > 0 && (
                <span className="meta-item">
                  <CheckCircle2 size={12} />
                  <span>{activity_summary.completed_week} completed</span>
                </span>
              )}
            </>
          )}
          {!activity_summary && (
            <span className="meta-item">
              <span className="meta-label">Created:</span>
              <span>{new Date(created_at).toLocaleDateString()}</span>
            </span>
          )}
        </div>
      </CardBody>
    </Card>
  )
}

export { ProjectIcon, ProjectLabels, ICON_MAP }
export default ProjectCard
