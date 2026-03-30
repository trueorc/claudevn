import DirectiveActionBar from './DirectiveActionBar'
import DirectiveStateMachine from './DirectiveStateMachine'
import PipelineStatus from './PipelineStatus'
import ConfidencePanel from './ConfidencePanel'
import DecompositionSummary from './DecompositionSummary'
import DependencyGraph from './DependencyGraph'
import WorkUnitList from './WorkUnitList'
import ComputeEnvironmentPanel from './ComputeEnvironmentPanel'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import { GitBranch } from 'lucide-react'

/**
 * Directive detail view — shows full decomposition for a single directive.
 *
 * Renders: action bar, state machine, pipeline, confidence, summary,
 * chains, work units, and environment.
 */
export default function DirectiveDetail({
  goal,
  workUnits,
  workUnitsLoading,
  pipelineData,
  qualityScores,
  chainAnalysis,
  computeEnv,
  unitScoreMap,
  onBack,
  onApprove,
  onRefine,
  onRefresh,
  onApproveEnvironment,
  approving,
  recomposing,
  envApproving,
}) {
  const hasWorkUnits = workUnits.length > 0
  const hasDraftUnits = hasWorkUnits && workUnits.some(u => u.status === 'draft')

  return (
    <div className="directive-detail">
      <DirectiveActionBar
        goal={goal}
        hasDraftUnits={hasDraftUnits}
        hasWorkUnits={hasWorkUnits}
        onBack={onBack}
        onApprove={onApprove}
        onRefine={onRefine}
        onRefresh={onRefresh}
        approving={approving}
        recomposing={recomposing}
      />

      {workUnitsLoading ? (
        <div className="goals-page-loading"><Spinner size="md" /></div>
      ) : !hasWorkUnits ? (
        <EmptyState
          icon={GitBranch}
          title="No Work Units Yet"
          description="This directive hasn't been decomposed yet. Use the chat to describe what you'd like done."
        />
      ) : (
        <div className="directive-detail-workspace">
          {hasWorkUnits && <DirectiveStateMachine workUnits={workUnits} pipelineData={pipelineData} />}

          {pipelineData && <PipelineStatus pipeline={pipelineData} />}

          {qualityScores && qualityScores.score !== undefined && (
            <ConfidencePanel scores={qualityScores} />
          )}

          <DecompositionSummary units={workUnits} />

          <DependencyGraph units={workUnits} chainAnalysis={chainAnalysis} />

          <ComputeEnvironmentPanel
            environment={computeEnv}
            onApprove={onApproveEnvironment}
            approving={envApproving}
          />

          <div className="goals-page-section">
            <div className="goals-page-section-header">
              <h2>Work Units</h2>
              <span className="goals-page-section-count">{workUnits.length}</span>
            </div>
            <WorkUnitList units={workUnits} unitScores={unitScoreMap} />
          </div>
        </div>
      )}
    </div>
  )
}
