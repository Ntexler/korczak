"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, ZoomIn, ZoomOut, Maximize2, ExternalLink } from "lucide-react";
import { getGraphVisualization } from "@/lib/api";
import ConnectionFeedback from "./ConnectionFeedback";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  confidence: number;
  color: string;
  definition?: string;
  paper_count?: number;
}

interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  confidence: number;
  explanation?: string;
  source_paper?: string;
}

interface SelectedInfo {
  node: GraphNode;
  connections: { node: GraphNode; edgeId: string; edgeType: string; direction: "to" | "from"; explanation?: string; source_paper?: string }[];
}

interface KnowledgeGraphProps {
  onClose: () => void;
}

const EDGE_COLORS: Record<string, string> = {
  RELATES_TO: "#2D3548",
  CONTRADICTS: "#F85149",
  SUPPORTS: "#3FB950",
  BUILDS_ON: "#58A6FF",
  RESPONDS_TO: "#D29922",
};

const EDGE_LABELS: Record<string, [string, string]> = {
  RELATES_TO: ["relates to", "קשור ל"],
  CONTRADICTS: ["contradicts", "סותר"],
  SUPPORTS: ["supports", "תומך ב"],
  BUILDS_ON: ["builds on", "מבוסס על"],
  RESPONDS_TO: ["responds to", "מגיב ל"],
};

const NODE_TYPES: { label: [string, string]; color: string }[] = [
  { label: ["Theory", "תאוריה"], color: "#E8B931" },
  { label: ["Method", "שיטה"], color: "#58A6FF" },
  { label: ["Concept", "מושג"], color: "#3FB950" },
  { label: ["Finding", "ממצא"], color: "#D29922" },
  { label: ["Person", "אישיות"], color: "#BC8CFF" },
  { label: ["Institution", "מוסד"], color: "#F78166" },
];

export default function KnowledgeGraph({ onClose }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [selected, setSelected] = useState<SelectedInfo | null>(null);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const setConceptPanelOpen = useChatStore((s) => s.setConceptPanelOpen);
  const { locale, t } = useLocaleStore();
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);

  const selectNode = useCallback((nodeId: string | null) => {
    if (!nodeId) {
      setSelected(null);
      return;
    }
    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;

    const connections: SelectedInfo["connections"] = [];
    for (const edge of edges) {
      const src = typeof edge.source === "string" ? edge.source : edge.source.id;
      const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
      if (src === nodeId) {
        const target = nodes.find((n) => n.id === tgt);
        if (target) connections.push({ node: target, edgeId: edge.id, edgeType: edge.type, direction: "to", explanation: edge.explanation, source_paper: edge.source_paper });
      } else if (tgt === nodeId) {
        const source = nodes.find((n) => n.id === src);
        if (source) connections.push({ node: source, edgeId: edge.id, edgeType: edge.type, direction: "from", explanation: edge.explanation, source_paper: edge.source_paper });
      }
    }

    setSelected({ node, connections });
  }, []);

  const highlightSelection = useCallback((nodeId: string | null) => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);

    if (!nodeId) {
      // Reset all
      svg.selectAll<SVGCircleElement, GraphNode>("circle.graph-node")
        .attr("opacity", 1)
        .attr("stroke", "#0C0F14")
        .attr("stroke-width", 1);
      svg.selectAll<SVGLineElement, GraphEdge>("line.graph-edge")
        .attr("stroke-opacity", 0.4)
        .attr("stroke-width", (d) => Math.max(0.5, d.confidence * 2));
      svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
        .attr("opacity", (d) => d.confidence > 0.7 ? 1 : 0);
      return;
    }

    const connectedIds = new Set<string>([nodeId]);
    for (const edge of edgesRef.current) {
      const src = typeof edge.source === "string" ? edge.source : edge.source.id;
      const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
      if (src === nodeId) connectedIds.add(tgt);
      if (tgt === nodeId) connectedIds.add(src);
    }

    // Dim unrelated nodes
    svg.selectAll<SVGCircleElement, GraphNode>("circle.graph-node")
      .attr("opacity", (d) => connectedIds.has(d.id) ? 1 : 0.15)
      .attr("stroke", (d) => d.id === nodeId ? "#E8B931" : connectedIds.has(d.id) ? "#E8B931" : "#0C0F14")
      .attr("stroke-width", (d) => d.id === nodeId ? 3 : connectedIds.has(d.id) ? 1.5 : 1);

    // Highlight connected edges, dim others
    svg.selectAll<SVGLineElement, GraphEdge>("line.graph-edge")
      .attr("stroke-opacity", (d) => {
        const src = typeof d.source === "string" ? d.source : d.source.id;
        const tgt = typeof d.target === "string" ? d.target : d.target.id;
        return (src === nodeId || tgt === nodeId) ? 0.9 : 0.05;
      })
      .attr("stroke-width", (d) => {
        const src = typeof d.source === "string" ? d.source : d.source.id;
        const tgt = typeof d.target === "string" ? d.target : d.target.id;
        return (src === nodeId || tgt === nodeId) ? Math.max(1.5, d.confidence * 3) : Math.max(0.5, d.confidence * 2);
      });

    // Show labels for connected nodes
    svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
      .attr("opacity", (d) => connectedIds.has(d.id) ? 1 : 0.1);

  }, []);

  const buildGraph = useCallback(async () => {
    if (!svgRef.current) return;

    setLoading(true);
    try {
      const data = await getGraphVisualization(150);
      const nodes: GraphNode[] = data.nodes;
      const edges: GraphEdge[] = data.edges;
      nodesRef.current = nodes;
      edgesRef.current = edges;
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

      // Click on background to deselect
      svg.on("click", (event) => {
        if (event.target === svgRef.current) {
          selectNode(null);
          highlightSelection(null);
        }
      });

      const container = svg.append("g");

      // Draw edges
      const link = container.append("g")
        .selectAll("line")
        .data(edges)
        .join("line")
        .attr("class", "graph-edge")
        .attr("stroke", (d) => EDGE_COLORS[d.type] || "#2D3548")
        .attr("stroke-width", (d) => Math.max(0.5, d.confidence * 2))
        .attr("stroke-opacity", 0.4);

      // Draw nodes
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
          selectNode(d.id);
          highlightSelection(d.id);
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

      // Labels for all nodes (only high-confidence visible by default)
      const labels = container.append("g")
        .selectAll("text")
        .data(nodes)
        .join("text")
        .attr("class", "graph-label")
        .text((d) => d.name.length > 22 ? d.name.slice(0, 20) + "..." : d.name)
        .attr("font-size", "8px")
        .attr("fill", "#8B949E")
        .attr("text-anchor", "middle")
        .attr("dy", (d) => -(6 + d.confidence * 4 + 2))
        .attr("pointer-events", "none")
        .attr("opacity", (d) => d.confidence > 0.7 ? 1 : 0);

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

      // Hover effects
      node
        .on("mouseenter", function (_event, d) {
          d3.select(this)
            .attr("r", 4 + d.confidence * 4 + 3)
            .attr("stroke", "#E8B931")
            .attr("stroke-width", 2);
          // Show label on hover
          labels.filter((ld) => ld.id === d.id).attr("opacity", 1);
        })
        .on("mouseleave", function (_event, d) {
          const isSelected = selected?.node.id === d.id;
          if (!isSelected) {
            d3.select(this)
              .attr("r", 4 + d.confidence * 4)
              .attr("stroke", "#0C0F14")
              .attr("stroke-width", 1);
          }
          // Hide label if it was hidden before
          labels.filter((ld) => ld.id === d.id && ld.confidence <= 0.7)
            .attr("opacity", (ld) => {
              // Keep visible if part of selection
              return 0;
            });
        });

    } catch (err) {
      console.error("Graph visualization error:", err);
    } finally {
      setLoading(false);
    }
  }, [selectNode, highlightSelection]);

  useEffect(() => {
    buildGraph();
    return () => {
      simulationRef.current?.stop();
    };
  }, [buildGraph]);

  // Toggle all labels
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    if (selected) return; // Don't override selection highlighting
    svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
      .attr("opacity", (d) => showAllLabels || d.confidence > 0.7 ? 1 : 0);
  }, [showAllLabels, selected]);

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

  const openConceptPanel = (conceptId: string) => {
    setSelectedConceptId(conceptId);
    setConceptPanelOpen(true);
    onClose();
  };

  const li = locale === "he" ? 1 : 0;

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-foreground">{t.knowledgeMap}</h2>
          <span className="text-xs text-text-secondary">
            {nodeCount} nodes &middot; {edgeCount} edges
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAllLabels(!showAllLabels)}
            className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              showAllLabels
                ? "bg-accent-gold/15 text-accent-gold"
                : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            {locale === "he" ? "תוויות" : "Labels"}
          </button>
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
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 border-b border-border text-[10px] text-text-secondary">
        <span className="font-semibold uppercase tracking-wider text-text-tertiary">
          {locale === "he" ? "סוגים:" : "Types:"}
        </span>
        {NODE_TYPES.map((item) => (
          <div key={item.label[0]} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            <span>{item.label[li]}</span>
          </div>
        ))}
        <span className="mx-1 text-border">|</span>
        <span className="font-semibold uppercase tracking-wider text-text-tertiary">
          {locale === "he" ? "קשרים:" : "Edges:"}
        </span>
        {Object.entries(EDGE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <span className="w-3 h-0.5 rounded" style={{ backgroundColor: color }} />
            <span>{EDGE_LABELS[type]?.[li] || type.toLowerCase()}</span>
          </div>
        ))}
      </div>

      {/* Graph + Info Panel */}
      <div className="flex-1 relative overflow-hidden">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex items-center gap-3 text-text-secondary">
              <div className="w-5 h-5 border-2 border-accent-gold border-t-transparent rounded-full animate-spin" />
              <span>{locale === "he" ? "בונה מפת ידע..." : "Building knowledge map..."}</span>
            </div>
          </div>
        )}

        {/* Hint text when nothing selected */}
        {!loading && !selected && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
            <div className="bg-surface/80 backdrop-blur-sm rounded-lg px-3 py-1.5 text-xs text-text-tertiary border border-border">
              {locale === "he" ? "לחץ על נקודה כדי לראות פרטים וחיבורים" : "Click any dot to see details and connections"}
            </div>
          </div>
        )}

        <svg ref={svgRef} className="w-full h-full" />

        {/* Info Panel — appears when a node is selected */}
        {selected && (
          <div
            className="absolute bottom-4 left-4 z-20 w-96 max-h-[70%] bg-surface border border-border rounded-xl shadow-lg overflow-hidden flex flex-col"
            dir={locale === "he" ? "rtl" : "ltr"}
          >
            {/* Selected node header */}
            <div className="px-4 py-3 border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: selected.node.color }} />
                  <h3 className="font-bold text-foreground truncate">{selected.node.name}</h3>
                </div>
                <button
                  onClick={() => { selectNode(null); highlightSelection(null); }}
                  className="p-1 rounded hover:bg-surface-hover text-text-secondary flex-shrink-0"
                >
                  <X size={14} />
                </button>
              </div>
              <div className="flex items-center gap-3 mt-1.5">
                <span className="text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded bg-surface-sunken text-text-secondary">
                  {selected.node.type}
                </span>
                {selected.node.paper_count ? (
                  <span className="text-[10px] text-text-tertiary">
                    {selected.node.paper_count} {t.papers}
                  </span>
                ) : null}
                <div className="flex items-center gap-1.5 flex-1">
                  <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent-gold rounded-full"
                      style={{ width: `${Math.round(selected.node.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-text-tertiary font-mono">
                    {Math.round(selected.node.confidence * 100)}%
                  </span>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Definition / Description paragraph */}
              {selected.node.definition && (
                <div className="px-4 py-3 border-b border-border/50">
                  <p className="text-xs text-text-secondary leading-relaxed">
                    {selected.node.definition}
                  </p>
                </div>
              )}

              {/* Explore in depth link */}
              <div className="px-4 pt-2">
                <button
                  onClick={() => openConceptPanel(selected.node.id)}
                  className="flex items-center gap-1.5 text-xs text-accent-gold hover:underline"
                >
                  <ExternalLink size={11} />
                  {locale === "he" ? "חקור לעומק בפאנל מושגים" : "Explore in depth"}
                </button>
              </div>

              {/* Connections with explanations */}
              <div className="px-4 py-2">
                <span className="text-[10px] uppercase tracking-wider font-semibold text-text-tertiary">
                  {t.connectedConcepts} ({selected.connections.length})
                </span>
              </div>
              {selected.connections.length === 0 ? (
                <div className="px-4 pb-3 text-xs text-text-tertiary">
                  {locale === "he" ? "אין חיבורים ישירים" : "No direct connections"}
                </div>
              ) : (
                <div className="px-2 pb-2 space-y-0.5">
                  {selected.connections.map((conn, i) => (
                    <button
                      key={`${conn.node.id}-${i}`}
                      onClick={() => {
                        selectNode(conn.node.id);
                        highlightSelection(conn.node.id);
                      }}
                      className="w-full px-2 py-2 rounded-lg hover:bg-surface-hover transition-colors text-left"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: conn.node.color }} />
                        <div className="min-w-0 flex-1">
                          <div className="text-xs text-foreground truncate">{conn.node.name}</div>
                          <div className="flex items-center gap-1 mt-0.5">
                            <span
                              className="w-2 h-0.5 rounded flex-shrink-0"
                              style={{ backgroundColor: EDGE_COLORS[conn.edgeType] || "#2D3548" }}
                            />
                            <span className="text-[10px] text-text-tertiary">
                              {conn.direction === "to"
                                ? (EDGE_LABELS[conn.edgeType]?.[li] || conn.edgeType.toLowerCase())
                                : (locale === "he" ? "מ: " : "from: ") + (EDGE_LABELS[conn.edgeType]?.[li] || conn.edgeType.toLowerCase())
                              }
                            </span>
                          </div>
                        </div>
                        <span className="text-[10px] text-text-tertiary font-mono flex-shrink-0">
                          {Math.round(conn.node.confidence * 100)}%
                        </span>
                      </div>
                      {/* Connection explanation — WHY these are connected */}
                      {conn.explanation && (
                        <p className="text-[10px] text-text-tertiary leading-relaxed mt-1 ml-4 italic">
                          {conn.explanation}
                        </p>
                      )}
                      {/* Source paper that established this connection */}
                      {conn.source_paper && (
                        <p className="text-[10px] text-accent-gold/60 mt-0.5 ml-4 truncate">
                          {locale === "he" ? "מקור: " : "Source: "}{conn.source_paper}
                        </p>
                      )}
                      {/* Agree/Disagree feedback */}
                      <div className="ml-4">
                        <ConnectionFeedback relationshipId={conn.edgeId} />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
