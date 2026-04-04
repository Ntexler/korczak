"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { getGraphVisualization } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  confidence: number;
  color: string;
}

interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  confidence: number;
}

interface KnowledgeGraphProps {
  onClose: () => void;
}

export default function KnowledgeGraph({ onClose }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);

  const buildGraph = useCallback(async () => {
    if (!svgRef.current) return;

    setLoading(true);
    try {
      const data = await getGraphVisualization(150);
      const nodes: GraphNode[] = data.nodes;
      const edges: GraphEdge[] = data.edges;
      setNodeCount(nodes.length);
      setEdgeCount(edges.length);

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();

      const width = svgRef.current.clientWidth;
      const height = svgRef.current.clientHeight;

      // Create zoom behavior
      const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 4])
        .on("zoom", (event) => {
          container.attr("transform", event.transform);
        });

      svg.call(zoom);

      const container = svg.append("g");

      // Edge type styles
      const edgeColors: Record<string, string> = {
        RELATES_TO: "#2D3548",
        CONTRADICTS: "#F85149",
        SUPPORTS: "#3FB950",
        BUILDS_ON: "#58A6FF",
        RESPONDS_TO: "#D29922",
      };

      // Draw edges
      const link = container.append("g")
        .selectAll("line")
        .data(edges)
        .join("line")
        .attr("stroke", (d) => edgeColors[d.type] || "#2D3548")
        .attr("stroke-width", (d) => Math.max(0.5, d.confidence * 2))
        .attr("stroke-opacity", 0.4);

      // Draw nodes
      const node = container.append("g")
        .selectAll("circle")
        .data(nodes)
        .join("circle")
        .attr("r", (d) => 4 + d.confidence * 4)
        .attr("fill", (d) => d.color)
        .attr("stroke", "#0C0F14")
        .attr("stroke-width", 1)
        .attr("cursor", "pointer")
        .on("click", (_event, d) => {
          setSelectedConceptId(d.id);
        });

      // Apply drag behavior
      const dragBehavior = d3.drag<SVGCircleElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulationRef.current?.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulationRef.current?.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (node as any).call(dragBehavior);

      // Labels (show on hover via title)
      node.append("title").text((d) => `${d.name} (${d.type})`);

      // Labels for high-confidence nodes
      const labels = container.append("g")
        .selectAll("text")
        .data(nodes.filter((n) => n.confidence > 0.7))
        .join("text")
        .text((d) => d.name.length > 20 ? d.name.slice(0, 18) + "..." : d.name)
        .attr("font-size", "8px")
        .attr("fill", "#8B949E")
        .attr("text-anchor", "middle")
        .attr("dy", -10)
        .attr("pointer-events", "none");

      // Force simulation
      const simulation = d3.forceSimulation<GraphNode>(nodes)
        .force("link", d3.forceLink<GraphNode, GraphEdge>(edges).id((d) => d.id).distance(60))
        .force("charge", d3.forceManyBody().strength(-80))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(12));

      simulationRef.current = simulation;

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

      // Highlight on hover
      node
        .on("mouseenter", function (_event, d) {
          d3.select(this)
            .attr("r", 4 + d.confidence * 4 + 3)
            .attr("stroke", "#E8B931")
            .attr("stroke-width", 2);
        })
        .on("mouseleave", function (_event, d) {
          d3.select(this)
            .attr("r", 4 + d.confidence * 4)
            .attr("stroke", "#0C0F14")
            .attr("stroke-width", 1);
        });

    } catch (err) {
      console.error("Graph visualization error:", err);
    } finally {
      setLoading(false);
    }
  }, [setSelectedConceptId]);

  useEffect(() => {
    buildGraph();
    return () => {
      simulationRef.current?.stop();
    };
  }, [buildGraph]);

  const handleZoom = (factor: number) => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const zoom = d3.zoom<SVGSVGElement, unknown>();
    svg.transition().duration(300).call(zoom.scaleBy, factor);
  };

  const handleFit = () => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const zoom = d3.zoom<SVGSVGElement, unknown>();
    svg.transition().duration(500).call(
      zoom.transform,
      d3.zoomIdentity.translate(svgRef.current.clientWidth / 2, svgRef.current.clientHeight / 2).scale(0.8)
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-foreground">Knowledge Map</h2>
          <span className="text-xs text-text-secondary">
            {nodeCount} nodes &middot; {edgeCount} edges
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => handleZoom(1.3)} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <ZoomIn size={16} />
          </button>
          <button onClick={() => handleZoom(0.7)} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <ZoomOut size={16} />
          </button>
          <button onClick={handleFit} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <Maximize2 size={16} />
          </button>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-border text-[10px] text-text-secondary">
        {[
          { label: "Theory", color: "#E8B931" },
          { label: "Method", color: "#58A6FF" },
          { label: "Concept", color: "#3FB950" },
          { label: "Finding", color: "#D29922" },
          { label: "Person", color: "#BC8CFF" },
          { label: "Institution", color: "#F78166" },
        ].map((item) => (
          <div key={item.label} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            <span>{item.label}</span>
          </div>
        ))}
      </div>

      {/* Graph */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex items-center gap-3 text-text-secondary">
              <div className="w-5 h-5 border-2 border-accent-gold border-t-transparent rounded-full animate-spin" />
              <span>Building knowledge map...</span>
            </div>
          </div>
        )}
        <svg ref={svgRef} className="w-full h-full" />
      </div>
    </div>
  );
}
