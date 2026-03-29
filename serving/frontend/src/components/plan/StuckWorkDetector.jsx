import { AlertTriangle, Clock, XCircle } from 'lucide-react'
import './StuckWorkDetector.css'

/**
 * Prominently surfaces work units that appear stuck or failed.
 * No silent failures — if something hasn't progressed, you see it here.
 */
export default function StuckWorkDetector({ items = [] }) {
  if (items.length === 0) return null

  const failed = items.filter(i => i.type === 'failed')
  const stuck = items.filter(i => i.type === 'stuck')
  const stale = items.filter(i => i.type === 'stale')

  return (
    <div className="swd-container">
      <div className="swd-header">
        <AlertTriangle size={14} className="swd-header-icon" />
        <span className="swd-title">Attention Required</span>
        <span className="swd-count">{items.length}</span>
      </div>

      <div className="swd-list">
        {failed.map((item, i) => (
          <div key={`f-${i}`} className="swd-item swd-item--failed">
            <XCircle size={14} />
            <div className="swd-item-content">
              <span className="swd-item-id">{item.work_unit_id || item.id}</span>
              <span className="swd-item-label">{item.description || 'Failed'}</span>
              {item.reason && <p className="swd-item-reason">{item.reason}</p>}
            </div>
            <span className="swd-item-duration">{item.duration || ''}</span>
          </div>
        ))}

        {stuck.map((item, i) => (
          <div key={`s-${i}`} className="swd-item swd-item--stuck">
            <Clock size={14} />
            <div className="swd-item-content">
              <span className="swd-item-id">{item.work_unit_id || item.id}</span>
              <span className="swd-item-label">{item.description || 'Stuck'}</span>
              <p className="swd-item-reason">
                In "{item.status}" for {item.duration} — no progress detected
              </p>
            </div>
          </div>
        ))}

        {stale.map((item, i) => (
          <div key={`st-${i}`} className="swd-item swd-item--stale">
            <Clock size={14} />
            <div className="swd-item-content">
              <span className="swd-item-id">{item.work_unit_id || item.id}</span>
              <span className="swd-item-label">{item.description || 'Stale'}</span>
              <p className="swd-item-reason">Last update {item.duration} ago</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
