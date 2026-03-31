import { Cpu, Clock } from 'lucide-react'

function formatElapsed(startedAt) {
  if (!startedAt) return ''
  const ms = Date.now() - new Date(startedAt).getTime()
  const secs = Math.floor(ms / 1000)
  const mins = Math.floor(secs / 60)
  if (mins > 0) return `${mins}m ${secs % 60}s`
  return `${secs}s`
}

/**
 * Shows running compute instances with their assigned work.
 */
export default function ActiveComputePanel({ executions = [] }) {
  if (executions.length === 0) return null

  return (
    <div className="exec-panel">
      <div className="exec-panel-header">
        <Cpu size={14} />
        <span className="exec-panel-title">Active Compute</span>
        <span className="exec-panel-count">{executions.length}</span>
      </div>
      <div className="exec-panel-list">
        {executions.map(exec => (
          <div key={exec.id} className="exec-panel-row exec-panel-row--active">
            <span className="exec-active-dot" />
            <span className="exec-panel-id">{exec.id?.slice(-8)}</span>
            <span className="exec-panel-desc">{exec.description?.slice(0, 30)}</span>
            {exec.instance_id && (
              <span className="exec-instance">{exec.instance_id.slice(-10)}</span>
            )}
            {exec.started_at && (
              <span className="exec-elapsed">
                <Clock size={10} /> {formatElapsed(exec.started_at)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
