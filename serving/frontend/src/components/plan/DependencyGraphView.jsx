import { useMemo } from 'react'
import WorkMapGraph from '../workmap/WorkMapGraph'

/**
 * Transforms plan summary items into graph data for WorkMapGraph.
 * Builds nodes from all plan items and edges from depends_on/blocks fields.
 */
function buildGraphData(data) {
  if (!data) return null

  const allItems = [
    ...(data.running_items || []),
    ...(data.queued_items || []),
    ...(data.blocked_items || []),
    ...(data.backlog_items || []),
    ...(data.failed_items || []),
    ...(data.done_items || []),
  ]

  if (allItems.length === 0) return null

  // Build nodes
  const nodes = allItems.map(item => ({
    id: item.issue_id,
    type: 'issue',
    title: item.title,
    status: item.status,
    number: item.number,
    priority: item.priority,
    goal_id: item.goal_id,
  }))

  // Collect unique goal IDs and add goal nodes
  const goalIds = new Set(allItems.map(i => i.goal_id).filter(Boolean))
  for (const goalId of goalIds) {
    nodes.push({
      id: goalId,
      type: 'goal',
      name: `Goal`,
      status: 'active',
    })
  }

  // Build edges
  const edges = []
  const nodeIds = new Set(nodes.map(n => n.id))

  for (const item of allItems) {
    // Goal membership edges
    if (item.goal_id && nodeIds.has(item.goal_id)) {
      edges.push({
        from: item.issue_id,
        to: item.goal_id,
        type: 'belongs_to',
      })
    }

    // Dependency edges
    if (item.depends_on) {
      for (const depId of item.depends_on) {
        if (nodeIds.has(depId)) {
          edges.push({
            from: item.issue_id,
            to: depId,
            type: 'depends_on',
          })
        }
      }
    }
  }

  return { nodes, edges }
}

function DependencyGraphView({ data, loading }) {
  const graphData = useMemo(() => buildGraphData(data), [data])

  return (
    <div className="plan-graph-view">
      <WorkMapGraph graphData={graphData} loading={loading} />
    </div>
  )
}

export default DependencyGraphView
