import { useState } from 'react'
import { AlertCircle, ChevronDown, ChevronRight, Lightbulb, ArrowLeftRight, HelpCircle, Layers } from 'lucide-react'
import './CoherencePanel.css'

const INSIGHT_ICONS = {
  contradiction: ArrowLeftRight,
  implicit_requirement: Lightbulb,
  scope_drift: Layers,
  gap: HelpCircle,
  unstated_dependency: AlertCircle,
}

const INSIGHT_LABELS = {
  contradiction: 'Contradiction',
  implicit_requirement: 'Implicit Requirement',
  scope_drift: 'Scope Drift',
  gap: 'Gap',
  unstated_dependency: 'Unstated Dependency',
}

const SEVERITY_ORDER = {
  high: 0,
  medium: 1,
  low: 2,
}

function InsightCard({ insight }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = INSIGHT_ICONS[insight.type] || AlertCircle

  return (
    <div className={`cp-insight cp-insight--${insight.severity || 'medium'}`}>
      <button className="cp-insight-header" onClick={() => setExpanded(!expanded)}>
        <Icon size={14} className="cp-insight-icon" />
        <span className={`cp-insight-type cp-insight-type--${insight.type}`}>
          {INSIGHT_LABELS[insight.type] || insight.type}
        </span>
        <span className="cp-insight-title">{insight.title}</span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {expanded && (
        <div className="cp-insight-body">
          <p className="cp-insight-description">{insight.description}</p>

          {/* What triggered this insight */}
          {insight.sources?.length > 0 && (
            <div className="cp-insight-sources">
              <span className="cp-insight-sources-label">From:</span>
              {insight.sources.map((src, i) => (
                <span key={i} className="cp-insight-source">
                  {src.goal_title || src.goal_id}
                  {src.excerpt && <span className="cp-insight-excerpt"> — "{src.excerpt}"</span>}
                </span>
              ))}
            </div>
          )}

          {/* Suggested resolution */}
          {insight.suggestion && (
            <div className="cp-insight-suggestion">
              <Lightbulb size={12} />
              <span>{insight.suggestion}</span>
            </div>
          )}

          {/* Affected work units */}
          {insight.affected_units?.length > 0 && (
            <div className="cp-insight-affected">
              <span className="cp-insight-affected-label">Affects:</span>
              {insight.affected_units.map((unitId, i) => (
                <span key={i} className="cp-insight-unit-tag">{unitId}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Goal coherence analysis panel.
 *
 * Watches for inconsistencies, implicit requirements, scope drift,
 * and gaps across all goals and steering input. Surfaces issues
 * that humans might miss when building up goals incrementally.
 *
 * Insights are produced by the backend coherence analyzer (Layer 1)
 * which compares new input against the existing goal corpus.
 */
export default function CoherencePanel({ insights = [], loading = false }) {
  const sorted = [...insights].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 1) - (SEVERITY_ORDER[b.severity] ?? 1)
  )

  const highCount = insights.filter(i => i.severity === 'high').length
  const hasIssues = insights.length > 0

  return (
    <div className="cp-panel">
      <div className="cp-panel-header">
        <AlertCircle size={14} className={hasIssues ? 'cp-header-icon--active' : 'cp-header-icon'} />
        <span className="cp-panel-title">Coherence</span>
        {highCount > 0 && (
          <span className="cp-panel-badge cp-panel-badge--high">{highCount}</span>
        )}
        {insights.length > 0 && highCount === 0 && (
          <span className="cp-panel-badge">{insights.length}</span>
        )}
      </div>

      {loading ? (
        <p className="cp-empty">Analyzing...</p>
      ) : !hasIssues ? (
        <p className="cp-empty cp-all-clear">No inconsistencies detected</p>
      ) : (
        <div className="cp-list">
          {sorted.map((insight, i) => (
            <InsightCard key={insight.id || i} insight={insight} />
          ))}
        </div>
      )}
    </div>
  )
}
