/**
 * DAG layout utilities — shared between ExecutionGraph and IssueDependencyGraph.
 *
 * Computes topological layers and (x,y) positions for rendering a
 * directed acyclic graph as an SVG.
 */

/**
 * Compute topological layers for a DAG.
 * Layer 0 = nodes with no dependencies, Layer N = max depth from roots.
 *
 * @param {Array} nodes — [{id, depends_on: [string]}]
 * @returns {Map<string, number>} nodeId → layer index
 */
export function computeLayers(nodes) {
  const nodeMap = new Map()
  nodes.forEach(n => nodeMap.set(n.id, n))

  const layers = new Map()
  const visited = new Set()

  function getLayer(id) {
    if (layers.has(id)) return layers.get(id)
    if (visited.has(id)) return 0 // cycle guard
    visited.add(id)

    const node = nodeMap.get(id)
    if (!node) return 0

    const deps = (node.depends_on || []).filter(d => nodeMap.has(d))
    if (deps.length === 0) {
      layers.set(id, 0)
      return 0
    }

    const maxDep = Math.max(...deps.map(d => getLayer(d)))
    const layer = maxDep + 1
    layers.set(id, layer)
    return layer
  }

  nodes.forEach(n => getLayer(n.id))
  return layers
}

/**
 * Compute (x, y) positions for each node based on layers.
 * Layers flow left-to-right. Nodes within a layer are vertically centered.
 *
 * @param {Array} nodes — [{id, ...}]
 * @param {Map} layers — from computeLayers()
 * @param {Object} opts — {nodeWidth, nodeHeight, layerGap, nodeGap}
 * @returns {Map<string, {x, y}>}
 */
export function computePositions(nodes, layers, opts = {}) {
  const {
    nodeWidth = 180,
    nodeHeight = 48,
    layerGap = 100,
    nodeGap = 16,
  } = opts

  const maxLayer = Math.max(0, ...layers.values())

  // Group nodes by layer
  const layerGroups = new Map()
  for (let i = 0; i <= maxLayer; i++) layerGroups.set(i, [])
  nodes.forEach(n => {
    const layer = layers.get(n.id) ?? 0
    layerGroups.get(layer)?.push(n)
  })

  const positions = new Map()

  for (let layer = 0; layer <= maxLayer; layer++) {
    const group = layerGroups.get(layer) || []
    const x = layer * (nodeWidth + layerGap) + 40
    const totalHeight = group.length * nodeHeight + (group.length - 1) * nodeGap
    const startY = Math.max(40, (400 - totalHeight) / 2) // center in ~400px viewport

    group.forEach((n, i) => {
      positions.set(n.id, {
        x,
        y: startY + i * (nodeHeight + nodeGap),
      })
    })
  }

  return positions
}

/**
 * Compute the critical path — longest chain through the DAG.
 *
 * @param {Array} nodes — [{id, depends_on, status}]
 * @returns {string[]} ordered list of node IDs on the critical path
 */
export function computeCriticalPath(nodes) {
  const nodeMap = new Map()
  nodes.forEach(n => nodeMap.set(n.id, n))

  // Build dependents map (reverse edges)
  const dependentsOf = new Map()
  nodes.forEach(n => {
    ;(n.depends_on || []).forEach(dep => {
      if (!dependentsOf.has(dep)) dependentsOf.set(dep, [])
      dependentsOf.get(dep).push(n.id)
    })
  })

  // Find roots
  const nodeIds = new Set(nodes.map(n => n.id))
  const roots = nodes.filter(n =>
    !(n.depends_on || []).some(d => nodeIds.has(d))
  )

  let longest = []

  function dfs(id, path) {
    const next = (dependentsOf.get(id) || []).filter(d => nodeIds.has(d))
    if (next.length === 0) {
      if (path.length > longest.length) longest = [...path]
      return
    }
    for (const dep of next) {
      dfs(dep, [...path, dep])
    }
  }

  for (const root of roots) {
    dfs(root.id, [root.id])
  }

  return longest
}

/**
 * Compute SVG dimensions needed for the graph.
 */
export function computeSvgSize(positions, opts = {}) {
  const { nodeWidth = 180, nodeHeight = 48, padding = 60 } = opts
  let maxX = 0, maxY = 0
  for (const { x, y } of positions.values()) {
    maxX = Math.max(maxX, x + nodeWidth)
    maxY = Math.max(maxY, y + nodeHeight)
  }
  return { width: maxX + padding, height: maxY + padding }
}
