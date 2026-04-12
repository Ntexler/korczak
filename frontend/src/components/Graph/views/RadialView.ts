import * as d3 from "d3";
import type { GraphNode, GraphEdge, ViewOptions, ViewCleanup, ViewRenderer } from "../types";

interface RadialNode {
  id: string;
  name: string;
  type: string;
  confidence: number;
  color: string;
  definition?: string;
  paper_count?: number;
  children: RadialNode[];
}

/**
 * Build a radial tree from any node as center, using ALL edge types.
 * BFS outward from root, max depth 4.
 */
function buildRadialTree(nodes: GraphNode[], edges: GraphEdge[], rootId: string): RadialNode | null {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const root = nodeMap.get(rootId);
  if (!root) return null;

  // Undirected adjacency
  const adj = new Map<string, string[]>();
  for (const edge of edges) {
    const src = typeof edge.source === "string" ? edge.source : edge.source.id;
    const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
    if (!adj.has(src)) adj.set(src, []);
    if (!adj.has(tgt)) adj.set(tgt, []);
    adj.get(src)!.push(tgt);
    adj.get(tgt)!.push(src);
  }

  const visited = new Set<string>();
  const toRadialNode = (nodeId: string, depth: number): RadialNode | null => {
    if (visited.has(nodeId) || depth > 4) return null;
    visited.add(nodeId);
    const n = nodeMap.get(nodeId);
    if (!n) return null;

    const children: RadialNode[] = [];
    const neighbors = adj.get(nodeId) || [];
    // Sort by confidence
    const sorted = [...new Set(neighbors)].sort((a, b) => {
      return (nodeMap.get(b)?.confidence || 0) - (nodeMap.get(a)?.confidence || 0);
    });

    for (const nid of sorted) {
      const child = toRadialNode(nid, depth + 1);
      if (child) children.push(child);
    }

    return {
      id: n.id, name: n.name, type: n.type, confidence: n.confidence,
      color: n.color, definition: n.definition, paper_count: n.paper_count,
      children,
    };
  };

  return toRadialNode(rootId, 0);
}

const renderRadialView: ViewRenderer = (svg, nodes, edges, options) => {
  const { width, height, onNodeClick, onBackgroundClick, rootNodeId } = options;
  const svgSel = d3.select(svg);
  svgSel.selectAll("*").remove();

  // Pick root
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

  const tree = buildRadialTree(nodes, edges, effectiveRoot);
  if (!tree) {
    svgSel.append("text")
      .attr("x", width / 2).attr("y", height / 2)
      .attr("text-anchor", "middle").attr("fill", "#8B949E")
      .text("Select a concept to see its neighborhood.");
    return {};
  }

  // Zoom
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => container.attr("transform", event.transform));
  svgSel.call(zoom);
  svgSel.on("click", (event) => { if (event.target === svg) onBackgroundClick(); });

  const container = svgSel.append("g");
  const cx = width / 2;
  const cy = height / 2;

  // Radial layout
  const radius = Math.min(width, height) / 2 - 80;
  const hierarchy = d3.hierarchy<RadialNode>(tree);
  const clusterLayout = d3.cluster<RadialNode>().size([2 * Math.PI, radius]);
  clusterLayout(hierarchy);

  // Draw concentric ring guides
  const maxDepth = hierarchy.height;
  for (let d = 1; d <= maxDepth; d++) {
    const r = (d / maxDepth) * radius;
    container.append("circle")
      .attr("cx", cx).attr("cy", cy).attr("r", r)
      .attr("fill", "none").attr("stroke", "#2D3548").attr("stroke-width", 0.5)
      .attr("stroke-dasharray", "3,3").attr("opacity", 0.3);
  }

  // Convert polar to cartesian
  const project = (angle: number, r: number): [number, number] => {
    return [cx + r * Math.cos(angle - Math.PI / 2), cy + r * Math.sin(angle - Math.PI / 2)];
  };

  // Draw links
  container.append("g")
    .selectAll("path")
    .data(hierarchy.links())
    .join("path")
    .attr("class", "graph-edge")
    .attr("d", (d) => {
      const [sx, sy] = project(d.source.x!, d.source.y!);
      const [tx, ty] = project(d.target.x!, d.target.y!);
      return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`;
    })
    .attr("fill", "none")
    .attr("stroke", "#2D3548")
    .attr("stroke-width", 1.2)
    .attr("stroke-opacity", 0.4);

  // Draw nodes
  const nodePositions = new Map<string, [number, number]>();
  const nodeGroups = container.append("g")
    .selectAll("g")
    .data(hierarchy.descendants())
    .join("g")
    .attr("transform", (d) => {
      const [x, y] = project(d.x!, d.y!);
      nodePositions.set(d.data.id, [x, y]);
      return `translate(${x},${y})`;
    })
    .attr("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      onNodeClick(d.data.id);
    });

  nodeGroups.append("circle")
    .attr("class", "graph-node")
    .attr("r", (d) => d.depth === 0 ? 10 : 4 + d.data.confidence * 4)
    .attr("fill", (d) => d.data.color)
    .attr("stroke", (d) => d.depth === 0 ? "#E8B931" : "#0C0F14")
    .attr("stroke-width", (d) => d.depth === 0 ? 3 : 1);

  // Labels
  nodeGroups.append("text")
    .attr("class", "graph-label")
    .text((d) => d.data.name)
    .attr("font-size", (d) => d.depth === 0 ? "10px" : "7px")
    .attr("fill", (d) => d.depth === 0 ? "#E8B931" : "#8B949E")
    .attr("text-anchor", "middle")
    .attr("dy", (d) => d.depth === 0 ? -(14) : -(6 + d.data.confidence * 4 + 2))
    .attr("pointer-events", "none")
    .attr("font-weight", (d) => d.depth === 0 ? "bold" : "normal")
    .attr("opacity", (d) => d.depth <= 1 || d.data.confidence > 0.7 ? 1 : 0);

  // Hover
  nodeGroups
    .on("mouseenter", function (_, d) {
      d3.select(this).select("circle")
        .attr("stroke", "#E8B931").attr("stroke-width", 2.5);
      d3.select(this).select("text").attr("opacity", 1);
    })
    .on("mouseleave", function (_, d) {
      d3.select(this).select("circle")
        .attr("stroke", d.depth === 0 ? "#E8B931" : "#0C0F14")
        .attr("stroke-width", d.depth === 0 ? 3 : 1);
      d3.select(this).select("text")
        .attr("opacity", d.depth <= 1 || d.data.confidence > 0.7 ? 1 : 0);
    });

  // Navigate to node
  const navigateToNode = (nodeId: string) => {
    const pos = nodePositions.get(nodeId);
    if (!pos) return;
    const transform = d3.zoomIdentity
      .translate(width / 2 - pos[0] * 1.5, height / 2 - pos[1] * 1.5)
      .scale(1.5);
    svgSel.transition().duration(500).call(zoom.transform, transform);
  };

  return { zoom, navigateToNode };
};

export default renderRadialView;
