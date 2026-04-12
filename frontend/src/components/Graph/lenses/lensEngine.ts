import * as d3 from "d3";
import type { GraphNode, GraphEdge, LensType, LensData, NodeOverride, EdgeOverride, ExtraLensElement } from "../types";

/**
 * Compute visual overrides for a given lens type.
 * The shell applies these overrides to SVG elements after the view renders.
 */
export function computeLens(
  lensType: LensType,
  nodes: GraphNode[],
  edges: GraphEdge[],
): LensData {
  switch (lensType) {
    case "confidence":
      return computeConfidenceLens(nodes, edges);
    case "recency":
      return computeRecencyLens(nodes, edges);
    case "controversy":
      return computeControversyLens(nodes, edges);
    case "community":
      return computeCommunityLens(nodes, edges);
    case "gap":
      return computeGapLens(nodes, edges);
    default:
      return { nodeOverrides: new Map(), edgeOverrides: new Map() };
  }
}

// --- Confidence Lens ---
// Node size scales with confidence. Edge width scales with confidence.
function computeConfidenceLens(nodes: GraphNode[], edges: GraphEdge[]): LensData {
  const nodeOverrides = new Map<string, NodeOverride>();
  const edgeOverrides = new Map<string, EdgeOverride>();

  for (const node of nodes) {
    const scale = 0.5 + node.confidence * 2; // 0.5x to 2.5x
    nodeOverrides.set(node.id, {
      radius: (4 + node.confidence * 4) * scale,
      opacity: 0.3 + node.confidence * 0.7,
    });
  }

  for (const edge of edges) {
    const scale = 0.5 + edge.confidence * 2.5;
    edgeOverrides.set(edge.id, {
      strokeWidth: Math.max(0.5, edge.confidence * 2) * scale,
      opacity: 0.15 + edge.confidence * 0.75,
    });
  }

  return { nodeOverrides, edgeOverrides };
}

// --- Recency Lens ---
// Fade old concepts, brighten new ones based on max_publication_year.
function computeRecencyLens(nodes: GraphNode[], edges: GraphEdge[]): LensData {
  const nodeOverrides = new Map<string, NodeOverride>();
  const edgeOverrides = new Map<string, EdgeOverride>();

  // Find year range
  const years = nodes.map((n) => n.max_publication_year).filter((y): y is number => y != null);
  if (years.length === 0) return { nodeOverrides, edgeOverrides };

  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const range = Math.max(maxYear - minYear, 1);

  const nodeYearMap = new Map<string, number>();
  for (const node of nodes) {
    const year = node.max_publication_year;
    if (year != null) {
      const t = (year - minYear) / range; // 0 = oldest, 1 = newest
      nodeYearMap.set(node.id, t);
      nodeOverrides.set(node.id, {
        opacity: 0.1 + t * 0.9,
        // Bright blue for new, dim for old
        stroke: t > 0.7 ? "#58A6FF" : undefined,
        strokeWidth: t > 0.7 ? 2 : undefined,
      });
    } else {
      nodeOverrides.set(node.id, { opacity: 0.15 });
    }
  }

  for (const edge of edges) {
    const srcId = typeof edge.source === "string" ? edge.source : edge.source.id;
    const tgtId = typeof edge.target === "string" ? edge.target : edge.target.id;
    const srcT = nodeYearMap.get(srcId) ?? 0;
    const tgtT = nodeYearMap.get(tgtId) ?? 0;
    const avgT = (srcT + tgtT) / 2;
    edgeOverrides.set(edge.id, {
      opacity: 0.05 + avgT * 0.85,
    });
  }

  return { nodeOverrides, edgeOverrides };
}

// --- Controversy Lens ---
// Red edges for disagreed connections, red node borders for high controversy_score.
function computeControversyLens(nodes: GraphNode[], edges: GraphEdge[]): LensData {
  const nodeOverrides = new Map<string, NodeOverride>();
  const edgeOverrides = new Map<string, EdgeOverride>();

  for (const node of nodes) {
    const score = node.controversy_score || 0;
    if (score > 0.6) {
      nodeOverrides.set(node.id, {
        stroke: "#F85149",
        strokeWidth: 1.5 + score * 2,
      });
    } else if (score > 0.3) {
      nodeOverrides.set(node.id, {
        stroke: "#D29922",
        strokeWidth: 1.5,
      });
    }
  }

  for (const edge of edges) {
    const disagrees = edge.disagree_count || 0;
    if (disagrees > 0) {
      // More disagrees → more red
      const intensity = Math.min(disagrees / 5, 1);
      edgeOverrides.set(edge.id, {
        stroke: intensity > 0.5 ? "#F85149" : "#D29922",
        strokeWidth: 1.5 + intensity * 2,
        opacity: 0.6 + intensity * 0.4,
      });
    }
  }

  return { nodeOverrides, edgeOverrides };
}

// --- Community Lens ---
// Glow/halo on nodes with high community activity (discussions + summaries).
function computeCommunityLens(nodes: GraphNode[], edges: GraphEdge[]): LensData {
  const nodeOverrides = new Map<string, NodeOverride>();
  const edgeOverrides = new Map<string, EdgeOverride>();

  const activities = nodes.map((n) => n.community_activity || 0);
  const maxActivity = Math.max(...activities, 1);

  for (const node of nodes) {
    const activity = node.community_activity || 0;
    if (activity > 0) {
      const t = Math.log(1 + activity) / Math.log(1 + maxActivity); // log scale
      nodeOverrides.set(node.id, {
        stroke: "#3FB950",
        strokeWidth: 1.5 + t * 3,
        opacity: 0.5 + t * 0.5,
        filter: t > 0.3 ? "community-glow" : undefined,
      });
    } else {
      nodeOverrides.set(node.id, { opacity: 0.25 });
    }
  }

  return { nodeOverrides, edgeOverrides };
}

// --- Gap Lens ---
// Highlight orphan nodes (few connections) in purple. Dim well-connected areas.
function computeGapLens(nodes: GraphNode[], edges: GraphEdge[]): LensData {
  const nodeOverrides = new Map<string, NodeOverride>();
  const edgeOverrides = new Map<string, EdgeOverride>();

  // Count connections per node
  const connectionCounts = new Map<string, number>();
  for (const edge of edges) {
    const src = typeof edge.source === "string" ? edge.source : edge.source.id;
    const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
    connectionCounts.set(src, (connectionCounts.get(src) || 0) + 1);
    connectionCounts.set(tgt, (connectionCounts.get(tgt) || 0) + 1);
  }

  for (const node of nodes) {
    const count = connectionCounts.get(node.id) || 0;
    if (count <= 1) {
      // Orphan / near-orphan — highlight as research opportunity
      nodeOverrides.set(node.id, {
        stroke: "#BC8CFF",
        strokeWidth: 2.5,
        radius: (4 + node.confidence * 4) * 1.5, // enlarged
        opacity: 1,
      });
    } else if (count <= 3) {
      // Low-connection — moderate highlight
      nodeOverrides.set(node.id, {
        stroke: "#BC8CFF",
        strokeWidth: 1.5,
        opacity: 0.8,
      });
    } else {
      // Well-connected — dim
      nodeOverrides.set(node.id, { opacity: 0.2 });
    }
  }

  // Dim all existing edges
  for (const edge of edges) {
    edgeOverrides.set(edge.id, { opacity: 0.1 });
  }

  return { nodeOverrides, edgeOverrides };
}

/**
 * Apply lens overrides to the SVG.
 * Call this after the view renderer has drawn the graph.
 */
export function applyLensToSvg(
  svg: SVGSVGElement,
  lensData: LensData,
): void {
  const svgSel = d3.select(svg);

  // Apply node overrides
  svgSel.selectAll<SVGCircleElement, { id: string }>("circle.graph-node")
    .each(function (d) {
      const override = lensData.nodeOverrides.get(d.id);
      if (!override) return;
      const el = d3.select(this);
      if (override.opacity != null) el.attr("opacity", override.opacity);
      if (override.radius != null) el.attr("r", override.radius);
      if (override.stroke != null) el.attr("stroke", override.stroke);
      if (override.strokeWidth != null) el.attr("stroke-width", override.strokeWidth);
    });

  // Apply edge overrides
  svgSel.selectAll<SVGLineElement, { id: string }>("line.graph-edge")
    .each(function (d) {
      const override = lensData.edgeOverrides.get(d.id);
      if (!override) return;
      const el = d3.select(this);
      if (override.opacity != null) el.attr("stroke-opacity", override.opacity);
      if (override.stroke != null) el.attr("stroke", override.stroke);
      if (override.strokeWidth != null) el.attr("stroke-width", override.strokeWidth);
      if (override.strokeDasharray != null) el.attr("stroke-dasharray", override.strokeDasharray);
    });

  // Also handle path-based edges (hierarchical/radial views use paths)
  svgSel.selectAll<SVGPathElement, { id?: string }>("path.graph-edge")
    .each(function (d) {
      if (!d?.id) return;
      const override = lensData.edgeOverrides.get(d.id);
      if (!override) return;
      const el = d3.select(this);
      if (override.opacity != null) el.attr("stroke-opacity", override.opacity);
      if (override.stroke != null) el.attr("stroke", override.stroke);
      if (override.strokeWidth != null) el.attr("stroke-width", override.strokeWidth);
    });
}
