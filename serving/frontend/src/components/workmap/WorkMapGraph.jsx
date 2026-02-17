import { useMemo } from 'react'
import { Target, Circle } from 'lucide-react'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './WorkMapGraph.css'

function WorkMapGraph({ graphData, loading }) {
  // Calculate node positions using force-directed layout approximation
  const layout = useMemo(() => {
    if (!graphData || !graphData.nodes || !graphData.edges) {
      return { nodes: [], edges: [] }
    }

    const nodes = graphData.nodes || []
    const edges = graphData.edges || []

    // Simple grid-based layout for goals and issues
    const goals = nodes.filter(n => n.type === 'goal')
    const issues = nodes.filter(n => n.type === 'issue')

    const layoutNodes = []

    // Position goals in left column
    goals.forEach((goal, i) => {
      const total = goals.length
      const spacing = total > 1 ? 80 / (total + 1) : 40
      const y = 10 + spacing * (i + 1)
      layoutNodes.push({
        ...goal,
        x: 20,
        y
      })
    })

    // Position issues in right column, grouped by goal
    const issuesByGoal = {}
    edges.forEach(edge => {
      if (edge.type === 'belongs_to') {
        if (!issuesByGoal[edge.from]) {
          issuesByGoal[edge.from] = []
        }
        issuesByGoal[edge.from].push(edge.to)
      }
    })

    let currentY = 10
    goals.forEach((goal, goalIndex) => {
      const goalIssues = issuesByGoal[goal.id] || []
      const goalNode = layoutNodes.find(n => n.id === goal.id)

      if (goalIssues.length > 0) {
        const issueSpacing = 8
        const startY = goalNode.y - (goalIssues.length - 1) * issueSpacing / 2

        goalIssues.forEach((issueId, issueIndex) => {
          const issue = issues.find(i => i.id === issueId)
          if (issue) {
            layoutNodes.push({
              ...issue,
              x: 70,
              y: startY + issueIndex * issueSpacing
            })
          }
        })
      }
    })

    // Add orphaned issues (not connected to any goal)
    const connectedIssueIds = new Set(Object.values(issuesByGoal).flat())
    const orphanedIssues = issues.filter(i => !connectedIssueIds.has(i.id))
    orphanedIssues.forEach((issue, i) => {
      layoutNodes.push({
        ...issue,
        x: 70,
        y: 85 + i * 5
      })
    })

    return { nodes: layoutNodes, edges }
  }, [graphData])

  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'done':
      case 'completed':
        return '#6b7280'
      case 'in_progress':
      case 'in_review':
        return '#3b82f6'
      case 'ready':
        return '#22c55e'
      case 'blocked':
        return '#ef4444'
      default:
        return '#71717a'
    }
  }

  const getStatusClass = (status) => {
    switch (status?.toLowerCase()) {
      case 'done':
      case 'completed':
        return 'status-done'
      case 'in_progress':
      case 'in_review':
        return 'status-progress'
      case 'ready':
        return 'status-ready'
      case 'blocked':
        return 'status-blocked'
      default:
        return 'status-default'
    }
  }

  if (loading) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  if (!layout.nodes || layout.nodes.length === 0) {
    return (
      <EmptyState
        icon={Circle}
        title="No graph data"
        description="Issue dependencies and goals will be visualized here"
      />
    )
  }

  // Calculate bezier curve path for edges
  const getBezierPath = (from, to) => {
    const x1 = from.x
    const y1 = from.y
    const x2 = to.x
    const y2 = to.y

    // Control points for smooth curve
    const controlX1 = x1 + (x2 - x1) * 0.5
    const controlY1 = y1
    const controlX2 = x1 + (x2 - x1) * 0.5
    const controlY2 = y2

    return `M ${x1} ${y1} C ${controlX1} ${controlY1}, ${controlX2} ${controlY2}, ${x2} ${y2}`
  }

  return (
    <div className="workmap-graph">
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" className="graph-svg">
        <defs>
          <marker
            id="arrowhead-dep"
            markerWidth="4"
            markerHeight="4"
            refX="3"
            refY="2"
            orient="auto"
          >
            <polygon points="0 0, 4 2, 0 4" fill="var(--border-light)" />
          </marker>

          <marker
            id="arrowhead-belongs"
            markerWidth="3"
            markerHeight="3"
            refX="2"
            refY="1.5"
            orient="auto"
          >
            <polygon points="0 0, 3 1.5, 0 3" fill="var(--text-muted)" opacity="0.5" />
          </marker>
        </defs>

        {/* Render edges */}
        {layout.edges.map((edge, i) => {
          const fromNode = layout.nodes.find(n => n.id === edge.from)
          const toNode = layout.nodes.find(n => n.id === edge.to)
          if (!fromNode || !toNode) return null

          const isDependency = edge.type === 'depends_on'
          const markerId = isDependency ? 'arrowhead-dep' : 'arrowhead-belongs'
          const className = isDependency ? 'edge edge-dependency' : 'edge edge-belongs'

          return (
            <path
              key={`edge-${i}`}
              d={getBezierPath(fromNode, toNode)}
              className={className}
              markerEnd={`url(#${markerId})`}
            />
          )
        })}

        {/* Render nodes */}
        {layout.nodes.map(node => {
          const isGoal = node.type === 'goal'
          const statusColor = getStatusColor(node.status)
          const statusClass = getStatusClass(node.status)

          return (
            <g
              key={node.id}
              className={`node ${isGoal ? 'node-goal' : 'node-issue'} ${statusClass}`}
              transform={`translate(${node.x}, ${node.y})`}
            >
              {isGoal ? (
                <>
                  <circle r="3.5" className="node-circle" fill={statusColor} />
                  <circle r="5" className="node-ring" />
                  <text x="-6" className="node-label node-label-left">
                    {node.name || node.title || `Goal ${node.id}`}
                  </text>
                </>
              ) : (
                <>
                  <circle r="2.5" className="node-circle" fill={statusColor} />
                  {node.status === 'blocked' && (
                    <circle r="4" className="node-blocked-ring" />
                  )}
                  <text x="4" className="node-label node-label-right">
                    #{node.number || node.id}
                  </text>
                </>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="graph-legend">
        <div className="legend-section">
          <span className="legend-title">Nodes</span>
          <div className="legend-item">
            <Target size={12} />
            <span>Goal</span>
          </div>
          <div className="legend-item">
            <Circle size={12} />
            <span>Issue</span>
          </div>
        </div>
        <div className="legend-section">
          <span className="legend-title">Status</span>
          <div className="legend-item">
            <span className="legend-dot status-ready"></span>
            <span>Ready</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot status-progress"></span>
            <span>In Progress</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot status-blocked"></span>
            <span>Blocked</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot status-done"></span>
            <span>Done</span>
          </div>
        </div>
        <div className="legend-section">
          <span className="legend-title">Edges</span>
          <div className="legend-item">
            <svg width="20" height="12" viewBox="0 0 20 12">
              <line x1="0" y1="6" x2="20" y2="6" stroke="var(--border-light)" strokeWidth="1.5" />
            </svg>
            <span>Depends on</span>
          </div>
          <div className="legend-item">
            <svg width="20" height="12" viewBox="0 0 20 12">
              <line x1="0" y1="6" x2="20" y2="6" stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2,2" opacity="0.5" />
            </svg>
            <span>Belongs to</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WorkMapGraph
