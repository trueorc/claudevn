import AttentionBanner from './AttentionBanner'
import ProjectStatsGrid from './ProjectStatsGrid'
import CoherencePanel from './CoherencePanel'
import ComputeEnvironmentPanel from './ComputeEnvironmentPanel'
import ComplexityProfile from './ComplexityProfile'
import DecompositionTimeline from './DecompositionTimeline'
import EmptyState from '../common/EmptyState'
import { GitBranch } from 'lucide-react'

/**
 * Project overview — aggregate view across all directives.
 *
 * Shows attention items, stats, coherence, environment,
 * complexity profile, and timeline.
 */
export default function ProjectOverview({
  goals,
  allWorkUnits,
  allScores,
  allChains,
  attentionItems,
  coherenceInsights,
  coherenceLoading,
  computeEnv,
  onApproveEnvironment,
  envApproving,
  onSelectGoal,
  decompEvents,
  summaryLoading,
}) {
  const hasDirectives = goals && goals.length > 0
  const hasDecompositions = allWorkUnits.size > 0

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

      {hasDecompositions && (
        <ProjectStatsGrid
          goals={goals}
          allWorkUnits={allWorkUnits}
          allScores={allScores}
        />
      )}

      <CoherencePanel insights={coherenceInsights} loading={coherenceLoading} />

      <ComputeEnvironmentPanel
        environment={computeEnv}
        onApprove={onApproveEnvironment}
        approving={envApproving}
      />

      {hasDecompositions && (
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
