import { deriveWorkflowState } from '../../hooks/useProjectDecompositionSummary'
import './DirectiveStateMachine.css'

const STEPS = [
  { key: 'draft', label: 'Draft' },
  { key: 'review', label: 'Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'executing', label: 'Executing' },
  { key: 'completed', label: 'Completed' },
]

const STEP_ORDER = STEPS.reduce((acc, s, i) => { acc[s.key] = i; return acc }, {})

/**
 * Horizontal workflow step indicator for a directive.
 * Shows: Draft → Review → Approved → Executing → Completed
 * Derived from work unit statuses.
 */
export default function DirectiveStateMachine({ workUnits, pipelineData }) {
  const state = deriveWorkflowState(workUnits, pipelineData)
  const activeIndex = STEP_ORDER[state] ?? 0

  return (
    <div className="dsm">
      {STEPS.map((step, i) => {
        const isComplete = i < activeIndex
        const isActive = i === activeIndex
        const isPending = i > activeIndex

        return (
          <div key={step.key} className="dsm-step-wrapper">
            {i > 0 && (
              <div className={`dsm-connector ${isComplete ? 'dsm-connector--done' : ''}`} />
            )}
            <div className={`dsm-step ${isComplete ? 'dsm-step--done' : ''} ${isActive ? 'dsm-step--active' : ''} ${isPending ? 'dsm-step--pending' : ''}`}>
              <div className="dsm-dot" />
              <span className="dsm-label">{step.label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
