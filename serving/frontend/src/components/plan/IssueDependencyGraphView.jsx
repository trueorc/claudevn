import { useMemo } from 'react'
import IssueDependencyGraph from '../workmap/IssueDependencyGraph'

/**
 * Transforms plan summary data into the graph format expected by
 * IssueDependencyGraph. Only issue nodes and depends_on edges are included
 * (goals are excluded to keep the view focused on inter-issue dependencies).
 */
function buildIssueGraphData(data) {
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

  const nodes = allItems.map(item => ({
    id: item.issue_id,
    type: 'issue',
    title: item.title,
    status: item.status,
    number: item.number,
    priority: item.priority,
  }))

  const nodeIds = new Set(nodes.map(n => n.id))
  const edges = []

  for (const item of allItems) {
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

function IssueDependencyGraphView({ data, loading }) {
  const graphData = useMemo(() => buildIssueGraphData(data), [data])

  return (
    <div className="plan-graph-view">
      <IssueDependencyGraph graphData={graphData} loading={loading} />
    </div>
  )
}

export default IssueDependencyGraphView
