import * as d3 from "d3";
import type { GraphNode, GraphEdge, ViewOptions, ViewCleanup, ViewRenderer } from "../types";
import { EDGE_COLORS } from "../types";

// Relationship types that imply hierarchy (parent → child direction)
const HIERARCHICAL_EDGE_TYPES = new Set([
  "BUILDS_ON", "PREREQUISITE_FOR", "PART_OF", "EXTENDS", "APPLIES",
]);

interface TreeNode {
  id: string;
  name: string;
  type: string;
  confidence: number;
  color: string;
  definition?: string;
  paper_count?: number;
  children: TreeNode[];
}

/**
 * Build a tree from flat nodes + edges via BFS from root.
 * Non-hierarchical edges and back-edges are ignored.
 */
function buildTree(nodes: GraphNode[], edges: GraphEdge[], rootId: string): TreeNode | null {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const root = nodeMap.get(rootId);
  if (!root) return null;

  // Build adjacency (only hierarchical edges)
  const children = new Map<string, { id: string; edgeType: string }[]>();
  for (const edge of edges) {
    const src = typeof edge.source === "string" ? edge.source : edge.source.id;
    const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
    if (!HIERARCHICAL_EDGE_TYPES.has(edge.type)) continue;
    // target BUILDS_ON source → source is parent, target is child
    if (!children.has(src)) children.set(src, []);
    children.get(src)!.push({ id: tgt, edgeType: edge.type });
    // Also add reverse for PREREQUISITE_FOR (source is prereq of target)
    if (!children.has(tgt)) children.set(tgt, []);
    children.get(tgt)!.push({ id: src, edgeType: edge.type });
  }

  // BFS to build tree (avoid cycles)
  const visited = new Set<string>();
  const toTreeNode = (nodeId: string, depth: number): TreeNode | null => {
    if (visited.has(nodeId) || depth > 6) return null;
    visited.add(nodeId);
    const n = nodeMap.get(nodeId);
    if (!n) return null;

    const childNodes: TreeNode[] = [];
    const adj = children.get(nodeId) || [];
    // Sort by confidence desc for consistent layout
    const sorted = adj.sort((a, b) => {
      const na = nodeMap.get(a.id);
      const nb = nodeMap.get(b.id);
      return (nb?.confidence || 0) - (na?.confidence || 0);
    });

    for (const { id } of sorted) {
      const child = toTreeNode(id, depth + 1);
      if (child) childNodes.push(child);
    }

    return {
      id: n.id,
      name: n.name,
      type: n.type,
      confidence: n.confidence,
      color: n.color,
      definition: n.definition,
      paper_count: n.paper_count,
      children: childNodes,
    };
  };

  return toTreeNode(rootId, 0);
}

const renderHierarchicalView: ViewRenderer = (svg, nodes, edges, options) => {
  const { width, height, onNodeClick, onBackgroundClick, rootNodeId } = options;
  const svgSel = d3.select(svg);
  svgSel.selectAll("*").remove();

  // Pick root: user-selected, or most-connected node
  const effectiveRoot = rootNodeId || (() => {
    const counts = new Map<string, number>();
    for (const e of edges) {
      const src = typeof e.source === "string" ? e.source : e.source.id;
      const tgt = typeof e.target === "string" ? e.target : e.target.id;
      counts.set(src, (counts.get(src) || 0) + 1);
      counts.set(tgt, (counts.get(tgt) || 0) + 1);
    }
    let best = nodes[0]?.id;
    let bestCount = 0;
    for (const [id, count] of counts) {
      if (count > bestCount) { best = id; bestCount = count; }
    }
    return best;
  })();

  const tree = buildTree(nodes, edges, effectiveRoot);
  if (!tree) {
    svgSel.append("text")
      .attr("x", width / 2).attr("y", height / 2)
      .attr("text-anchor", "middle").attr("fill", "#8B949E")
      .text("No hierarchical structure found. Select a root concept.");
    return {};
  }

  // Zoom
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => container.attr("transform", event.transform));
  svgSel.call(zoom);
  svgSel.on("click", (event) => { if (event.target === svg) onBackgroundClick(); });

  const container = svgSel.append("g");

  // D3 tree layout
  const hierarchy = d3.hierarchy<TreeNode>(tree);
  const treeLayout = d3.tree<TreeNode>().size([width - 120, height - 120]);
  treeLayout(hierarchy);

  // Draw links (curved bezier)
  container.append("g")
    .selectAll("path")
    .data(hierarchy.links())
    .join("path")
    .attr("class", "graph-edge")
    .attr("d", (d) => {
      const sx = d.source.x! + 60;
      const sy = d.source.y! + 60;
      const tx = d.target.x! + 60;
      const ty = d.target.y! + 60;
      const my = (sy + ty) / 2;
      return `M${sx},${sy} C${sx},${my} ${tx},${my} ${tx},${ty}`;
    })
    .attr("fill", "none")
    .attr("stroke", "#2D3548")
    .attr("stroke-width", 1.5)
    .attr("stroke-opacity", 0.5);

  // Draw nodes
  const nodeGroups = container.append("g")
    .selectAll("g")
    .data(hierarchy.descendants())
    .join("g")
    .attr("transform", (d) => `translate(${d.x! + 60},${d.y! + 60})`)
    .attr("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      onNodeClick(d.data.id);
    });

  nodeGroups.append("circle")
    .attr("class", "graph-node")
    .attr("r", (d) => 5 + d.data.confidence * 5)
    .attr("fill", (d) => d.data.color)
    .attr("stroke", (d) => d.depth === 0 ? "#E8B931" : "#0C0F14")
    .attr("stroke-width", (d) => d.depth === 0 ? 2.5 : 1);

  nodeGroups.append("text")
    .attr("class", "graph-label")
    .text((d) => d.data.name)
    .attr("font-size", "8px")
    .attr("fill", "#8B949E")
    .attr("text-anchor", "middle")
    .attr("dy", (d) => -(7 + d.data.confidence * 5 + 2))
    .attr("pointer-events", "none")
    .attr("opacity", (d) => d.depth <= 2 || d.data.confidence > 0.7 ? 1 : 0);

  // Hover effects
  nodeGroups
    .on("mouseenter", function (_, d) {
      d3.select(this).select("circle")
        .attr("stroke", "#E8B931").attr("stroke-width", 2.5)
        .attr("r", 5 + d.data.confidence * 5 + 3);
      d3.select(this).select("text").attr("opacity", 1);
    })
    .on("mouseleave", function (_, d) {
      d3.select(this).select("circle")
        .attr("stroke", d.depth === 0 ? "#E8B931" : "#0C0F14")
        .attr("stroke-width", d.depth === 0 ? 2.5 : 1)
        .attr("r", 5 + d.data.confidence * 5);
      d3.select(this).select("text")
        .attr("opacity", d.depth <= 2 || d.data.confidence > 0.7 ? 1 : 0);
    });

  // Center the tree
  svgSel.call(zoom.transform, d3.zoomIdentity.translate(0, 20).scale(0.85));

  // Navigate to node
  const nodePositions = new Map<string, { x: number; y: number }>();
  hierarchy.descendants().forEach((d) => {
    nodePositions.set(d.data.id, { x: d.x! + 60, y: d.y! + 60 });
  });

  const navigateToNode = (nodeId: string) => {
    const pos = nodePositions.get(nodeId);
    if (!pos) return;
    const transform = d3.zoomIdentity
      .translate(width / 2 - pos.x * 1.5, height / 2 - pos.y * 1.5)
      .scale(1.5);
    svgSel.transition().duration(500).call(zoom.transform, transform);
  };

  return { zoom, navigateToNode };
};

export default renderHierarchicalView;
