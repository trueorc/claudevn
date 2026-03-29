import { useNavigate } from 'react-router-dom'
import { Play, Clock, CheckCircle2, ChevronRight } from 'lucide-react'
import './ExecutionStrip.css'

/**
 * Layer 2 compact strip — shows what's running and what's next.
 * Not a control panel, just visibility.
 */
export default function ExecutionStrip({ active = [], queued = [], completed = 0 }) {
  const navigate = useNavigate()

  return (
    <button className="es-strip" onClick={() => navigate('/execute')}>
      <div className="es-strip-header">
        <span className="es-strip-title">Execution</span>
        <ChevronRight size={14} className="es-strip-chevron" />
      </div>
      <div className="es-strip-counts">
        <span className="es-count es-count--active">
          <Play size={12} /> {active.length} running
        </span>
        <span className="es-count es-count--queued">
          <Clock size={12} /> {queued.length} queued
        </span>
        <span className="es-count es-count--done">
          <CheckCircle2 size={12} /> {completed} done
        </span>
      </div>
      {active.length > 0 && (
        <div className="es-active-list">
          {active.slice(0, 3).map((unit) => (
            <div key={unit.id} className="es-active-item">
              <span className="es-active-dot" />
              <span className="es-active-id">{unit.id}</span>
              <span className="es-active-desc">{unit.description?.slice(0, 40)}</span>
            </div>
          ))}
        </div>
      )}
    </button>
  )
}
