import './EmptyState.css'

function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="empty-state">
      {Icon && <Icon size={40} strokeWidth={1} className="empty-icon" />}
      {title && <h3 className="empty-title">{title}</h3>}
      {description && <p className="empty-description">{description}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  )
}

export default EmptyState
