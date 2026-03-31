import AttentionBanner from './AttentionBanner'
import ProjectStatsGrid from './ProjectStatsGrid'
import PlanConflictsPanel from './PlanConflictsPanel'
import CoherencePanel from './CoherencePanel'
import ComputeEnvironmentPanel from './ComputeEnvironmentPanel'
import UnifiedWorkUnitList from './UnifiedWorkUnitList'
import ComplexityProfile from './ComplexityProfile'
import DecompositionTimeline from './DecompositionTimeline'
import EmptyState from '../common/EmptyState'
import { GitBranch } from 'lucide-react'

/**
 * Project overview — the unified project plan view.
 *
 * Shows the current desired state of the project: all active work units
 * across directives, superseded units, conflicts, coherence, and timeline.
 */
export default function ProjectOverview({
  goals,
  // Unified plan data
  activeUnits,
  supersededUnits,
  conflicts,
  // Per-directive data (for complexity profile + scores)
  allWorkUnits,
  allScores,
  allChains,
  // Attention + coherence
  attentionItems,
  coherenceInsights,
  coherenceLoading,
  // Environment
  computeEnv,
  onApproveEnvironment,
  envApproving,
  // Actions
  onSelectGoal,
  onResolveConflict,
  conflictResolving,
  // Timeline
  decompEvents,
  summaryLoading,
}) {
  const hasDirectives = goals && goals.length > 0
  const hasUnits = activeUnits && activeUnits.length > 0

  if (!hasDirectives) {
    return (
      <EmptyState
        icon={GitBranch}
        title="No Directives"
        description="Use the chat to describe what you'd like to build. The system will decompose it into formally specified work units."
      />
    )
  }

  return (
    <div className="project-overview">
      <AttentionBanner items={attentionItems} onSelectGoal={onSelectGoal} />

      {hasUnits && (
        <ProjectStatsGrid
          goals={goals}
          allWorkUnits={allWorkUnits}
          allScores={allScores}
          activeUnits={activeUnits}
          supersededCount={supersededUnits?.length || 0}
        />
      )}

      <PlanConflictsPanel
        conflicts={conflicts}
        allUnits={[...(activeUnits || []), ...(supersededUnits || [])]}
        onResolve={onResolveConflict}
        resolving={conflictResolving}
      />

      <CoherencePanel insights={coherenceInsights} loading={coherenceLoading} />

      <ComputeEnvironmentPanel
        environment={computeEnv}
        onApprove={onApproveEnvironment}
        approving={envApproving}
      />

      {hasUnits && (
        <UnifiedWorkUnitList
          activeUnits={activeUnits}
          supersededUnits={supersededUnits}
          goals={goals}
          onSelectGoal={onSelectGoal}
        />
      )}

      {hasDirectives && allWorkUnits?.size > 0 && (
        <ComplexityProfile
          goals={goals}
          allWorkUnits={allWorkUnits}
          allScores={allScores}
          onSelectGoal={onSelectGoal}
        />
      )}

      <DecompositionTimeline events={decompEvents} />
    </div>
  )
}
