import './Card.css'

function Card({ children, className = '', onClick }) {
  return (
    <div
      className={`card ${onClick ? 'card-clickable' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children }) {
  return <div className="card-header">{children}</div>
}

export function CardBody({ children }) {
  return <div className="card-body">{children}</div>
}

export default Card
