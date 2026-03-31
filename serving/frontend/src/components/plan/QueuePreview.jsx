import { Clock } from 'lucide-react'

/**
 * Queue preview — shows the next units to be dispatched.
 */
export default function QueuePreview({ items = [] }) {
  if (items.length === 0) return null

  return (
    <div className="exec-panel">
      <div className="exec-panel-header">
        <Clock size={14} />
        <span className="exec-panel-title">Up Next</span>
        <span className="exec-panel-count">{items.length}</span>
      </div>
      <div className="exec-panel-list">
        {items.slice(0, 8).map(item => (
          <div key={item.id} className="exec-panel-row">
            {item.complexity && (
              <span className={`exec-complexity exec-complexity--${item.complexity}`}>
                {item.complexity.toUpperCase()}
              </span>
            )}
            <span className="exec-panel-id">{item.id?.slice(-8)}</span>
            <span className="exec-panel-desc">{item.description?.slice(0, 40)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
