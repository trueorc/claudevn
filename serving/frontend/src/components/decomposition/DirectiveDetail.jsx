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
  reconciliation,
  onBack,
  onApprove,
  onRefine,
  onRefresh,
  onRetry,
  onApproveEnvironment,
  approving,
  recomposing,
  retrying,
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
        onRetry={onRetry}
        approving={approving}
        recomposing={recomposing}
        retrying={retrying}
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

          {reconciliation && (reconciliation.supersessions?.length > 0 || reconciliation.conflicts?.length > 0) && (
            <div className="directive-contribution">
              <span className="directive-contribution-title">This directive:</span>
              {reconciliation.new_unit_ids?.length > 0 && (
                <span className="directive-contrib-item directive-contrib--new">
                  + {reconciliation.new_unit_ids.length} new unit{reconciliation.new_unit_ids.length !== 1 ? 's' : ''}
                </span>
              )}
              {reconciliation.supersessions?.length > 0 && (
                <span className="directive-contrib-item directive-contrib--superseded">
                  ~ {reconciliation.supersessions.length} superseded
                </span>
              )}
              {reconciliation.conflicts?.filter(c => !c.resolved).length > 0 && (
                <span className="directive-contrib-item directive-contrib--conflict">
                  ! {reconciliation.conflicts.filter(c => !c.resolved).length} conflict{reconciliation.conflicts.filter(c => !c.resolved).length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          )}

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
