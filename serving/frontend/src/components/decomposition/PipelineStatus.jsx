import { CheckCircle2, XCircle, Clock, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import './PipelineStatus.css'

const STEP_LABELS = {
  llm_decompose: 'LLM Decomposition',
  codebase_analysis: 'Codebase Analysis',
  build_work_units: 'Build Work Units',
  validate: 'Validate Independence',
  analyze_environment: 'Analyze Environment',
}

const STATUS_ICONS = {
  completed: CheckCircle2,
  failed: XCircle,
  running: Loader2,
  pending: Clock,
}

function StepRow({ step }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = STATUS_ICONS[step.status] || Clock
  const label = STEP_LABELS[step.name] || step.name
  const hasDetail = step.detail || step.error

  return (
    <div className={`ps-step ps-step--${step.status}`}>
      <button className="ps-step-header" onClick={() => hasDetail && setExpanded(!expanded)}>
        <Icon size={14} className={`ps-step-icon ${step.status === 'running' ? 'ps-step-icon--spin' : ''}`} />
        <span className="ps-step-label">{label}</span>
        {step.duration_ms != null && (
          <span className="ps-step-duration">{step.duration_ms}ms</span>
        )}
        <span className={`ps-step-status ps-step-status--${step.status}`}>
          {step.status}
        </span>
        {hasDetail && (expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
      </button>
      {expanded && (
        <div className="ps-step-detail">
          {step.detail && <p className="ps-step-detail-text">{step.detail}</p>}
          {step.error && <p className="ps-step-error-text">{step.error}</p>}
        </div>
      )}
    </div>
  )
}

/**
 * Shows the v2.0 decomposition pipeline progress.
 * Each step (LLM → Analyze → Build → Validate → Environment) shows
 * its status with timing, details on expand, and error info on failure.
 */
export default function PipelineStatus({ pipeline }) {
  if (!pipeline || !pipeline.steps || pipeline.steps.length === 0) return null

  const completedCount = pipeline.steps.filter(s => s.status === 'completed').length
  const failedCount = pipeline.steps.filter(s => s.status === 'failed').length
  const totalSteps = pipeline.steps.length

  return (
    <div className={`ps-container ${failedCount > 0 ? 'ps-container--has-failure' : ''}`}>
      <div className="ps-header">
        <span className="ps-title">Decomposition Pipeline</span>
        <span className="ps-progress">
          {completedCount}/{totalSteps} steps
          {failedCount > 0 && <span className="ps-failed-badge">{failedCount} failed</span>}
        </span>
      </div>
      <div className="ps-steps">
        {pipeline.steps.map((step, i) => (
          <StepRow key={step.name || i} step={step} />
        ))}
      </div>
      {pipeline.work_unit_count > 0 && (
        <div className="ps-summary">
          {pipeline.work_unit_count} work units produced
        </div>
      )}
    </div>
  )
}
