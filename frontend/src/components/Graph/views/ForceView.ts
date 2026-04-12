import * as d3 from "d3";
import type { GraphNode, GraphEdge, ViewOptions, ViewCleanup, ViewRenderer } from "../types";
import { EDGE_COLORS } from "../types";

const renderForceView: ViewRenderer = (svg, nodes, edges, options) => {
  const { width, height, onNodeClick, onBackgroundClick } = options;
  const svgSel = d3.select(svg);
  svgSel.selectAll("*").remove();

  // Zoom behavior
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => {
      container.attr("transform", event.transform);
    });

  svgSel.call(zoom);

  // Background click to deselect
  svgSel.on("click", (event) => {
    if (event.target === svg) onBackgroundClick();
  });

  const container = svgSel.append("g");

  // Edges
  const link = container.append("g")
    .selectAll("line")
    .data(edges)
    .join("line")
    .attr("class", "graph-edge")
    .attr("stroke", (d) => EDGE_COLORS[d.type] || "#2D3548")
    .attr("stroke-width", (d) => Math.max(0.5, d.confidence * 2))
    .attr("stroke-opacity", 0.4);

  // Nodes
  const node = container.append("g")
    .selectAll("circle")
    .data(nodes)
    .join("circle")
    .attr("class", "graph-node")
    .attr("r", (d) => 4 + d.confidence * 4)
    .attr("fill", (d) => d.color)
    .attr("stroke", "#0C0F14")
    .attr("stroke-width", 1)
    .attr("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      onNodeClick(d.id);
    });

  // Drag behavior
  const dragBehavior = d3.drag<SVGCircleElement, GraphNode>()
    .on("start", (event, d) => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (event, d) => {
      d.fx = event.x;
      d.fy = event.y;
    })
    .on("end", (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (node as any).call(dragBehavior);

  // Labels
  const labels = container.append("g")
    .selectAll("text")
    .data(nodes)
    .join("text")
    .attr("class", "graph-label")
    .text((d) => d.name)
    .attr("font-size", "8px")
    .attr("fill", "#8B949E")
    .attr("text-anchor", "middle")
    .attr("dy", (d) => -(6 + d.confidence * 4 + 2))
    .attr("pointer-events", "none")
    .attr("opacity", (d) => d.confidence > 0.7 ? 1 : 0);

  // Hover effects
  node
    .on("mouseenter", function (_event, d) {
      d3.select(this)
        .attr("r", 4 + d.confidence * 4 + 3)
        .attr("stroke", "#E8B931")
        .attr("stroke-width", 2);
      labels.filter((ld) => ld.id === d.id).attr("opacity", 1);
    })
    .on("mouseleave", function (_event, d) {
      d3.select(this)
        .attr("r", 4 + d.confidence * 4)
        .attr("stroke", "#0C0F14")
        .attr("stroke-width", 1);
      labels.filter((ld) => ld.id === d.id && ld.confidence <= 0.7)
        .attr("opacity", 0);
    });

  // Force simulation
  const simulation = d3.forceSimulation<GraphNode>(nodes)
    .force("link", d3.forceLink<GraphNode, GraphEdge>(edges).id((d) => d.id).distance(60))
    .force("charge", d3.forceManyBody().strength(-80))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(12));

  simulation.on("tick", () => {
    link
      .attr("x1", (d) => (d.source as GraphNode).x!)
      .attr("y1", (d) => (d.source as GraphNode).y!)
      .attr("x2", (d) => (d.target as GraphNode).x!)
      .attr("y2", (d) => (d.target as GraphNode).y!);

    node
      .attr("cx", (d) => d.x!)
      .attr("cy", (d) => d.y!);

    labels
      .attr("x", (d) => d.x!)
      .attr("y", (d) => d.y!);
  });

  // Navigate-to-node helper
  const navigateToNode = (nodeId: string) => {
    const target = nodes.find((n) => n.id === nodeId);
    if (!target || target.x == null || target.y == null) return;
    const transform = d3.zoomIdentity
      .translate(width / 2 - target.x * 1.5, height / 2 - target.y * 1.5)
      .scale(1.5);
    svgSel.transition().duration(500).call(zoom.transform, transform);
  };

  return { simulation, zoom, navigateToNode };
};

export default renderForceView;
