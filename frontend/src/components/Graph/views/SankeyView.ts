import * as d3 from "d3";
import { sankey as d3Sankey, sankeyLinkHorizontal, SankeyNode, SankeyLink } from "d3-sankey";
import type { GraphNode, GraphEdge, ViewOptions, ViewCleanup, ViewRenderer } from "../types";
import { NODE_TYPES } from "../types";

interface SankeyFlow {
  source_type: string;
  target_type: string;
  relationship_type: string;
  count: number;
}

const TYPE_COLORS: Record<string, string> = {};
for (const t of NODE_TYPES) {
  TYPE_COLORS[t.type] = t.color;
}

const renderSankeyView: ViewRenderer = (svg, nodes, edges, options) => {
  const { width, height, onBackgroundClick } = options;
  const svgSel = d3.select(svg);
  svgSel.selectAll("*").remove();

  // Zoom
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.3, 4])
    .on("zoom", (event) => container.attr("transform", event.transform));
  svgSel.call(zoom);
  svgSel.on("click", (event) => { if (event.target === svg) onBackgroundClick(); });

  const container = svgSel.append("g");
  const margin = { top: 30, right: 40, bottom: 30, left: 40 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  container.attr("transform", `translate(${margin.left},${margin.top})`);

  // Fetch Sankey data from API
  import("@/lib/api").then(({ getSankeyFlowData }) => {
    getSankeyFlowData().then((data: { flows: SankeyFlow[]; types: string[] }) => {
      if (data.flows.length === 0) {
        container.append("text")
          .attr("x", innerWidth / 2).attr("y", innerHeight / 2)
          .attr("text-anchor", "middle").attr("fill", "#8B949E").attr("font-size", "14px")
          .text("No flow data available.");
        return;
      }

      // Build sankey nodes: source types on left, target types on right
      // To show flow direction, prefix with "src_" and "tgt_"
      const sourceTypes = new Set(data.flows.map((f) => f.source_type));
      const targetTypes = new Set(data.flows.map((f) => f.target_type));
      const allNodeNames: string[] = [];
      const nodeIndexMap = new Map<string, number>();

      for (const t of sourceTypes) {
        const key = `src_${t}`;
        nodeIndexMap.set(key, allNodeNames.length);
        allNodeNames.push(key);
      }
      for (const t of targetTypes) {
        const key = `tgt_${t}`;
        if (!nodeIndexMap.has(key)) {
          nodeIndexMap.set(key, allNodeNames.length);
          allNodeNames.push(key);
        }
      }

      const sankeyNodes = allNodeNames.map((name) => ({ name }));

      // Aggregate flows (merge relationship types)
      const flowMap = new Map<string, number>();
      for (const f of data.flows) {
        const key = `src_${f.source_type}->tgt_${f.target_type}`;
        flowMap.set(key, (flowMap.get(key) || 0) + f.count);
      }

      const sankeyLinks = Array.from(flowMap.entries()).map(([key, value]) => {
        const [srcKey, tgtKey] = key.split("->");
        return {
          source: nodeIndexMap.get(srcKey) || 0,
          target: nodeIndexMap.get(tgtKey) || 0,
          value,
        };
      }).filter((l) => l.source !== l.target); // Remove self-links

      if (sankeyLinks.length === 0) {
        container.append("text")
          .attr("x", innerWidth / 2).attr("y", innerHeight / 2)
          .attr("text-anchor", "middle").attr("fill", "#8B949E")
          .text("No cross-type relationships found.");
        return;
      }

      // D3 Sankey layout
      interface SNode { name: string; }
      interface SLink { source: number; target: number; value: number; }

      const sankeyLayout = d3Sankey<SNode, SLink>()
        .nodeWidth(20)
        .nodePadding(12)
        .extent([[0, 0], [innerWidth, innerHeight]]);

      const graph = sankeyLayout({
        nodes: sankeyNodes.map((d) => ({ ...d })),
        links: sankeyLinks.map((d) => ({ ...d })),
      });

      // Draw links
      container.append("g")
        .selectAll("path")
        .data(graph.links)
        .join("path")
        .attr("d", sankeyLinkHorizontal())
        .attr("fill", "none")
        .attr("stroke", (d: any) => {
          const srcName = (d.source as any).name.replace("src_", "");
          return TYPE_COLORS[srcName] || "#2D3548";
        })
        .attr("stroke-opacity", 0.35)
        .attr("stroke-width", (d: any) => Math.max(1, d.width))
        .on("mouseenter", function () {
          d3.select(this).attr("stroke-opacity", 0.7);
        })
        .on("mouseleave", function () {
          d3.select(this).attr("stroke-opacity", 0.35);
        });

      // Draw nodes (rectangles)
      container.append("g")
        .selectAll("rect")
        .data(graph.nodes)
        .join("rect")
        .attr("x", (d: any) => d.x0)
        .attr("y", (d: any) => d.y0)
        .attr("height", (d: any) => Math.max(1, d.y1 - d.y0))
        .attr("width", (d: any) => d.x1 - d.x0)
        .attr("fill", (d: any) => {
          const typeName = d.name.replace(/^(src_|tgt_)/, "");
          return TYPE_COLORS[typeName] || "#8B949E";
        })
        .attr("rx", 3)
        .attr("opacity", 0.9);

      // Node labels
      container.append("g")
        .selectAll("text")
        .data(graph.nodes)
        .join("text")
        .attr("x", (d: any) => d.x0 < innerWidth / 2 ? d.x1 + 8 : d.x0 - 8)
        .attr("y", (d: any) => (d.y0 + d.y1) / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", (d: any) => d.x0 < innerWidth / 2 ? "start" : "end")
        .attr("fill", "#E6EDF3")
        .attr("font-size", "11px")
        .text((d: any) => {
          const typeName = d.name.replace(/^(src_|tgt_)/, "");
          const prefix = d.name.startsWith("src_") ? "" : "";
          return prefix + typeName;
        });

      // Title
      container.append("text")
        .attr("x", innerWidth / 2).attr("y", -10)
        .attr("text-anchor", "middle")
        .attr("fill", "#8B949E").attr("font-size", "12px")
        .text("Idea Flow Between Concept Types");
    });
  });

  return { zoom };
};

export default renderSankeyView;
