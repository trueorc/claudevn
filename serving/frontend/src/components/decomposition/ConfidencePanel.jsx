import { useState } from 'react'
import { Gauge, ChevronDown, ChevronRight, Scissors, Merge, AlertTriangle, Info } from 'lucide-react'
import './ConfidencePanel.css'

const LEVEL_CONFIG = {
  green: { label: 'Ready', className: 'cp-level--green' },
  yellow: { label: 'Needs Review', className: 'cp-level--yellow' },
  red: { label: 'Not Ready', className: 'cp-level--red' },
}

const FACTOR_LABELS = {
  average_unit_score: 'Average Unit Score',
  independence_rate: 'Independence Rate',
  dependency_validity: 'Dependency Validity',
  criteria_coverage: 'Criteria Coverage',
  interface_chains: 'Interface Chains',
  validation_errors: 'Validation Errors',
}

export default function ConfidencePanel({ scores }) {
  const [expandedFactor, setExpandedFactor] = useState(null)

  if (!scores || scores.score === undefined) return null

  const levelInfo = LEVEL_CONFIG[scores.level] || LEVEL_CONFIG.red
  const recommendations = scores.recommendations || []
  const factors = scores.factors || []

  return (
    <div className={`cp ${levelInfo.className}`}>
      {/* Header with traffic light */}
      <div className="cp-header">
        <div className="cp-traffic-light">
          <div className={`cp-light cp-light--${scores.level}`} />
          <div className="cp-score-group">
            <span className="cp-score">{scores.score}</span>
            <span className="cp-score-label">/100</span>
          </div>
          <span className="cp-level-label">{levelInfo.label}</span>
        </div>
        <Gauge size={18} className="cp-icon" />
      </div>

      {/* Factor breakdown */}
      <div className="cp-factors">
        {factors.map((factor) => {
          const isExpanded = expandedFactor === factor.name
          return (
            <div key={factor.name} className="cp-factor">
              <button
                className="cp-factor-header"
                onClick={() => setExpandedFactor(isExpanded ? null : factor.name)}
              >
                <span className="cp-factor-name">
                  {FACTOR_LABELS[factor.name] || factor.name}
                </span>
                <div className="cp-factor-bar-container">
                  <div
                    className={`cp-factor-bar ${barClass(factor.score)}`}
                    style={{ width: `${factor.score}%` }}
                  />
                </div>
                <span className="cp-factor-score">{factor.score}</span>
                <span className="cp-factor-weight">{Math.round(factor.weight * 100)}%</span>
                {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              </button>
              {isExpanded && (
                <div className="cp-factor-detail">{factor.detail}</div>
              )}
            </div>
          )
        })}
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="cp-recommendations">
          <span className="cp-rec-title">
            <Info size={12} /> Recommendations
          </span>
          {recommendations.map((rec, i) => (
            <div key={i} className={`cp-rec cp-rec--${rec.type}`}>
              {rec.type === 'split' ? <Scissors size={12} /> : <Merge size={12} />}
              <div className="cp-rec-body">
                <span className="cp-rec-reason">{rec.reason}</span>
                {rec.unit_ids?.length > 0 && (
                  <span className="cp-rec-units">{rec.unit_ids.join(', ')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function barClass(score) {
  if (score >= 80) return 'cp-bar--good'
  if (score >= 60) return 'cp-bar--ok'
  if (score >= 40) return 'cp-bar--warn'
  return 'cp-bar--bad'
}

/**
 * Compact score badge for use in WorkUnitCard headers.
 */
export function ScoreBadge({ score }) {
  if (score === null || score === undefined) return null
  let cls = 'cp-badge--bad'
  if (score >= 80) cls = 'cp-badge--good'
  else if (score >= 60) cls = 'cp-badge--ok'
  else if (score >= 40) cls = 'cp-badge--warn'

  return <span className={`cp-badge ${cls}`}>{score}</span>
}
