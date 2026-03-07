import './NotificationDot.css'

function NotificationDot({ color = 'red', title }) {
  const className = `notification-dot notification-dot--${color}`
  return <span className={className} title={title} aria-label={title} />
}

export default NotificationDot
