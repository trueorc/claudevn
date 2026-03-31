import { useState } from 'react'
import {
  GitBranch, Play, ShieldCheck, AlertTriangle, CheckCircle2,
  XCircle, Clock, ArrowRight, ChevronDown, ChevronRight, Filter,
  Cpu, Zap, AlertCircle
} from 'lucide-react'
import './EventActivityLog.css'

const EVENT_CONFIG = {
  'decomposition.started': { icon: GitBranch, label: 'Decomposition started', layer: 'L1' },
  'decomposition.updated': { icon: GitBranch, label: 'Decomposition updated', layer: 'L1' },
  'decomposition.approved': { icon: CheckCircle2, label: 'Decomposition approved', layer: 'L1' },
  'decomposition.feedback': { icon: AlertTriangle, label: 'Decomposition feedback', layer: 'L1' },
  'execution.queued': { icon: Clock, label: 'Queued for execution', layer: 'L2' },
  'execution.started': { icon: Play, label: 'Execution started', layer: 'L2' },
  'execution.completed': { icon: CheckCircle2, label: 'Execution completed', layer: 'L2' },
  'execution.failed': { icon: XCircle, label: 'Execution failed', layer: 'L2' },
  'verification.started': { icon: ShieldCheck, label: 'Verification started', layer: 'L3' },
  'verification.completed': { icon: CheckCircle2, label: 'Verification passed', layer: 'L3' },
  'verification.failed': { icon: XCircle, label: 'Verification failed', layer: 'L3' },
  'verification.integration_conflict': { icon: AlertTriangle, label: 'Integration conflict', layer: 'L3' },
  // Compute lifecycle
  'compute.instance_registered': { icon: Cpu, label: 'Compute registered', layer: 'SYS' },
  'compute.instance_removed': { icon: Cpu, label: 'Compute removed', layer: 'SYS' },
  'compute.instance_approved': { icon: CheckCircle2, label: 'Compute approved', layer: 'SYS' },
  'compute.health_changed': { icon: AlertTriangle, label: 'Health changed', layer: 'SYS' },
  'compute.connected': { icon: Zap, label: 'Compute connected', layer: 'SYS' },
  'compute.disconnected': { icon: XCircle, label: 'Compute disconnected', layer: 'SYS' },
  'compute.drain_started': { icon: Clock, label: 'Drain started', layer: 'SYS' },
  // Work lifecycle
  'work.ready_for_dispatch': { icon: ArrowRight, label: 'Work ready', layer: 'L2' },
  'work.stuck_detected': { icon: AlertTriangle, label: 'Work stuck', layer: 'L2' },
  'work.timeout_recovered': { icon: Play, label: 'Timeout recovered', layer: 'L2' },
  'work.timeout_failed': { icon: XCircle, label: 'Timeout failed', layer: 'L2' },
  // Errors
  'error.mcp_tool': { icon: AlertCircle, label: 'MCP tool error', layer: 'ERR' },
  'error.dispatch': { icon: AlertCircle, label: 'Dispatch error', layer: 'ERR' },
  'error.health_check': { icon: AlertCircle, label: 'Health check error', layer: 'ERR' },
  'error.sse_connection': { icon: AlertCircle, label: 'SSE error', layer: 'ERR' },
}

const LAYER_COLORS = {
  L1: 'var(--primary)',
  L2: 'var(--status-degraded)',
  L3: 'var(--status-online)',
  SYS: 'var(--text-muted)',
  ERR: 'var(--status-offline)',
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const d = new Date(timestamp)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function EventRow({ event }) {
  const config = EVENT_CONFIG[event.event] || { icon: ArrowRight, label: event.event, layer: '?' }
  const Icon = config.icon
  const isFailed = event.event?.includes('failed') || event.event?.includes('conflict')

  return (
    <div className={`eal-row ${isFailed ? 'eal-row--failed' : ''}`}>
      <span className="eal-time">{formatTime(event.timestamp)}</span>
      <span className="eal-layer" style={{ color: LAYER_COLORS[config.layer] || 'var(--text-muted)' }}>
        {config.layer}
      </span>
      <Icon size={14} className={`eal-icon ${isFailed ? 'eal-icon--failed' : ''}`} />
      <span className="eal-label">{config.label}</span>
      {event.work_unit_id && (
        <span className="eal-unit-id">{event.work_unit_id}</span>
      )}
      {event.goal_id && (
        <span className="eal-goal-id">{event.goal_id}</span>
      )}
      {event.reason && (
        <span className="eal-reason">{event.reason}</span>
      )}
      {event.details && (
        <span className="eal-reason">{event.details}</span>
      )}
    </div>
  )
}

/**
 * Real-time event activity log — surfaces every layer transition.
 * Nothing fails silently when this is visible.
 */
export default function EventActivityLog({ events = [] }) {
  const [filterLayer, setFilterLayer] = useState(null)
  const [expanded, setExpanded] = useState(true)

  const filtered = filterLayer
    ? events.filter(e => {
        const config = EVENT_CONFIG[e.event]
        return config?.layer === filterLayer
      })
    : events

  const failedCount = events.filter(e => e.event?.includes('failed') || e.event?.includes('conflict')).length

  return (
    <div className="eal-container">
      <button className="eal-header" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="eal-title">Activity Log</span>
        <span className="eal-count">{events.length} events</span>
        {failedCount > 0 && (
          <span className="eal-failed-badge">{failedCount} failed</span>
        )}
      </button>

      {expanded && (
        <>
          <div className="eal-filters">
            <button
              className={`eal-filter-btn ${filterLayer === null ? 'eal-filter-btn--active' : ''}`}
              onClick={() => setFilterLayer(null)}
            >
              All
            </button>
            {['L1', 'L2', 'L3'].map(layer => (
              <button
                key={layer}
                className={`eal-filter-btn ${filterLayer === layer ? 'eal-filter-btn--active' : ''}`}
                onClick={() => setFilterLayer(filterLayer === layer ? null : layer)}
                style={filterLayer === layer ? { color: LAYER_COLORS[layer] } : {}}
              >
                {layer}
              </button>
            ))}
          </div>
          <div className="eal-list">
            {filtered.length === 0 ? (
              <p className="eal-empty">No events yet — activity will appear here in real time</p>
            ) : (
              filtered.slice(0, 100).map((event, i) => (
                <EventRow key={event.id || `${event.event}-${event.timestamp}-${i}`} event={event} />
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}
