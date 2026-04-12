"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, ZoomIn, ZoomOut, Maximize2, ExternalLink, Search, ChevronRight, BookOpen, MessageSquare, Filter } from "lucide-react";
import { getGraphVisualization, getConceptDetail } from "@/lib/api";
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

const NODE_TYPES: { type: string; label: [string, string]; color: string }[] = [
  { type: "theory", label: ["Theory", "תאוריה"], color: "#E8B931" },
  { type: "method", label: ["Method", "שיטה"], color: "#58A6FF" },
  { type: "framework", label: ["Framework", "מסגרת"], color: "#3FB950" },
  { type: "phenomenon", label: ["Phenomenon", "תופעה"], color: "#D29922" },
  { type: "paradigm", label: ["Paradigm", "פרדיגמה"], color: "#E8B931" },
  { type: "critique", label: ["Critique", "ביקורת"], color: "#F85149" },
  { type: "tool", label: ["Tool", "כלי"], color: "#BC8CFF" },
  { type: "metric", label: ["Metric", "מדד"], color: "#F78166" },
];

export default function KnowledgeGraph({ onClose }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [selected, setSelected] = useState<SelectedInfo | null>(null);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GraphNode[]>([]);
  const [fontSize, setFontSize] = useState(1); // 0=small, 1=medium, 2=large
  const [conceptDetail, setConceptDetail] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [navHistory, setNavHistory] = useState<{ id: string; name: string }[]>([]);
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const setConceptPanelOpen = useChatStore((s) => s.setConceptPanelOpen);
  const { locale, t } = useLocaleStore();
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);

  const selectNode = useCallback((nodeId: string | null, addToHistory = true) => {
    if (!nodeId) {
      setSelected(null);
      setConceptDetail(null);
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

    // Track navigation path
    if (addToHistory) {
      setNavHistory((prev) => {
        const already = prev.findIndex((h) => h.id === nodeId);
        if (already >= 0) return prev.slice(0, already + 1);
        return [...prev.slice(-4), { id: nodeId, name: node.name }];
      });
    }

    // Fetch full concept detail (key papers, claims) for learning
    setLoadingDetail(true);
    setConceptDetail(null);
    getConceptDetail(nodeId)
      .then((detail) => setConceptDetail(detail))
      .catch(() => setConceptDetail(null))
      .finally(() => setLoadingDetail(false));
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
      zoomRef.current = zoom;

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
        .text((d) => d.name)
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

  // Filter nodes by type
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll<SVGCircleElement, GraphNode>("circle.graph-node")
      .attr("opacity", (d) => hiddenTypes.has(d.type) ? 0.04 : 1)
      .attr("pointer-events", (d) => hiddenTypes.has(d.type) ? "none" : "auto");
    svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
      .attr("opacity", (d) => hiddenTypes.has(d.type) ? 0 : (showAllLabels || d.confidence > 0.7 ? 1 : 0));
    svg.selectAll<SVGLineElement, GraphEdge>("line.graph-edge")
      .attr("stroke-opacity", (d) => {
        const srcNode = nodesRef.current.find((n) => n.id === (typeof d.source === "string" ? d.source : d.source.id));
        const tgtNode = nodesRef.current.find((n) => n.id === (typeof d.target === "string" ? d.target : d.target.id));
        if (srcNode && hiddenTypes.has(srcNode.type)) return 0.02;
        if (tgtNode && hiddenTypes.has(tgtNode.type)) return 0.02;
        return 0.4;
      });
  }, [hiddenTypes, showAllLabels]);

  const handleZoom = (factor: number) => {
    if (!svgRef.current || !zoomRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.transition().duration(300).call(zoomRef.current.scaleBy, factor);
  };

  const handleFit = () => {
    if (!svgRef.current || !zoomRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.transition().duration(500).call(
      zoomRef.current.transform,
      d3.zoomIdentity.translate(svgRef.current.clientWidth / 2, svgRef.current.clientHeight / 2).scale(0.8)
    );
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    const q = query.toLowerCase();
    const results = nodesRef.current
      .filter((n) => n.name.toLowerCase().includes(q))
      .sort((a, b) => b.confidence - a.confidence)
      .slice(0, 8);
    setSearchResults(results);
  };

  const navigateToNode = (nodeId: string) => {
    if (!svgRef.current || !zoomRef.current) return;
    const node = nodesRef.current.find((n) => n.id === nodeId);
    if (!node || node.x == null || node.y == null) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const transform = d3.zoomIdentity
      .translate(width / 2 - node.x * 1.5, height / 2 - node.y * 1.5)
      .scale(1.5);
    svg.transition().duration(500).call(zoomRef.current.transform, transform);

    selectNode(nodeId);
    highlightSelection(nodeId);
    setSearchQuery("");
    setSearchResults([]);
  };

  const openConceptPanel = (conceptId: string) => {
    setSelectedConceptId(conceptId);
    setConceptPanelOpen(true);
    onClose();
  };

  // Navigate to node AND zoom to it (used by breadcrumb + connections)
  const navAndSelect = (nodeId: string) => {
    navigateToNode(nodeId);
  };

  const li = locale === "he" ? 1 : 0;
  const textSizes = ["text-sm", "text-[15px]", "text-lg"];
  const bodySize = textSizes[fontSize];
  const subSize = ["text-xs", "text-sm", "text-[15px]"][fontSize];

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
          {/* Search */}
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder={locale === "he" ? "חפש מושג..." : "Find concept..."}
              className="w-48 pl-8 pr-3 py-1.5 bg-surface-sunken border border-border-subtle rounded-lg
                text-sm text-foreground placeholder:text-text-tertiary
                focus:outline-none focus:border-accent-gold/40 focus:ring-1 focus:ring-accent-gold/15"
            />
            {searchResults.length > 0 && (
              <div className="absolute top-full mt-1 left-0 w-64 bg-surface border border-border rounded-lg shadow-lg z-30 max-h-60 overflow-y-auto">
                {searchResults.map((node) => (
                  <button
                    key={node.id}
                    onClick={() => navigateToNode(node.id)}
                    className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-surface-hover transition-colors"
                  >
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: node.color }} />
                    <span className="text-sm text-foreground truncate">{node.name}</span>
                    <span className="text-xs text-text-tertiary ml-auto">{node.type}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              showFilters || hiddenTypes.size > 0
                ? "bg-accent-gold/15 text-accent-gold"
                : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            <Filter size={12} />
            {locale === "he" ? "סינון" : "Filter"}
            {hiddenTypes.size > 0 && (
              <span className="ml-0.5 px-1 py-px rounded-full bg-accent-gold/20 text-[9px]">
                {hiddenTypes.size}
              </span>
            )}
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

      {/* Filter bar — clickable type toggles */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-border bg-surface/50">
          <span className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mr-1">
            {locale === "he" ? "סנן סוגים:" : "Filter types:"}
          </span>
          {NODE_TYPES.map((item) => {
            const isHidden = hiddenTypes.has(item.type);
            return (
              <button
                key={item.type}
                onClick={() => {
                  setHiddenTypes((prev) => {
                    const next = new Set(prev);
                    if (next.has(item.type)) next.delete(item.type);
                    else next.add(item.type);
                    return next;
                  });
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                  isHidden
                    ? "opacity-40 bg-surface-sunken text-text-tertiary line-through"
                    : "bg-surface-hover text-foreground"
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: isHidden ? "#3A3F47" : item.color }} />
                {item.label[li]}
              </button>
            );
          })}
          {hiddenTypes.size > 0 && (
            <button
              onClick={() => setHiddenTypes(new Set())}
              className="px-2 py-1 rounded-full text-[10px] font-medium text-accent-gold hover:bg-accent-gold/10 transition-colors"
            >
              {locale === "he" ? "הצג הכל" : "Show all"}
            </button>
          )}
        </div>
      )}

      {/* Edge legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 border-b border-border text-[10px] text-text-secondary">
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

        {/* Orientation panel when nothing selected */}
        {!loading && !selected && (
          <div
            className={`absolute top-4 z-10 w-[30rem] bg-surface/95 backdrop-blur-sm border border-border rounded-xl shadow-lg overflow-y-auto max-h-[80%] ${
              locale === "he" ? "right-4" : "left-4"
            }`}
            dir={locale === "he" ? "rtl" : "ltr"}
          >
            <div className="px-5 py-4 border-b border-border">
              <h3 className="text-lg font-bold text-foreground mb-1">
                {locale === "he" ? "מפת הידע" : "Knowledge Map"}
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                {locale === "he"
                  ? "מפה זו מציגה את כל המושגים, התאוריות, השיטות והתופעות בגרף הידע שלנו — וכיצד הם מתחברים זה לזה."
                  : "This map shows all the concepts, theories, methods, and phenomena in the knowledge graph — and how they connect to each other."}
              </p>
            </div>
            <div className="px-5 py-3 space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-1.5">
                  {locale === "he" ? "מה אתה רואה" : "What you're seeing"}
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {locale === "he"
                    ? "כל נקודה היא מושג אקדמי. הצבע מציין את הסוג (תאוריה, שיטה, מסגרת, תופעה וכו'). הגודל והבהירות משקפים את רמת הביטחון — כמה מבוסס המושג על עדויות. הקווים מראים קשרים: תמיכה, סתירה, המשכיות או תגובה."
                    : "Each dot is an academic concept. The color indicates its type (theory, method, framework, phenomenon, etc.). Size and brightness reflect confidence level — how well-established the concept is based on evidence. Lines show relationships: support, contradiction, building-on, or responding-to."}
                </p>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-1.5">
                  {locale === "he" ? "איך לנווט" : "How to navigate"}
                </h4>
                <ul className="text-sm text-text-secondary space-y-1 leading-relaxed">
                  <li>{locale === "he" ? "• לחץ על נקודה כדי לקרוא עליה לעומק — הגדרה, מאמרים מרכזיים, טענות וחיבורים" : "• Click any dot to read about it in depth — definition, key papers, claims, and connections"}</li>
                  <li>{locale === "he" ? "• לחץ על מושג מחובר כדי לנווט אליו ולהמשיך לחקור" : "• Click a connected concept to navigate there and keep exploring"}</li>
                  <li>{locale === "he" ? "• השתמש בחיפוש למעלה כדי למצוא מושג ספציפי" : "• Use the search bar above to find a specific concept"}</li>
                  <li>{locale === "he" ? "• גלגל עכבר או כפתורי הזום כדי להתקרב ולהתרחק" : "• Mouse wheel or zoom buttons to zoom in and out"}</li>
                  <li>{locale === "he" ? "• גרור את הרקע כדי להזיז את המפה" : "• Drag the background to pan around"}</li>
                </ul>
              </div>
              <div className="pt-1">
                <h4 className="text-sm font-semibold text-foreground mb-1.5">
                  {locale === "he" ? "סוגי מושגים" : "Concept types"}
                </h4>
                <div className="grid grid-cols-2 gap-1.5">
                  {NODE_TYPES.map((item) => (
                    <div key={item.label[0]} className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                      <span className="text-sm text-text-secondary">{item.label[li]}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-border/50 bg-surface-sunken/30">
              <p className="text-xs text-accent-gold text-center">
                {locale === "he" ? "בחר מושג כדי להתחיל ללמוד" : "Select a concept to start learning"}
              </p>
            </div>
          </div>
        )}

        <svg ref={svgRef} className="w-full h-full" />

        {/* Info Panel — appears when a node is selected */}
        {selected && (
          <div
            className={`absolute top-4 z-20 w-[34rem] max-h-[90%] bg-surface border border-border rounded-xl shadow-lg overflow-hidden flex flex-col ${
              locale === "he" ? "right-4" : "left-4"
            }`}
            dir={locale === "he" ? "rtl" : "ltr"}
          >
            {/* Navigation breadcrumb + controls */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-border/50 bg-surface-sunken/50">
              {/* Breadcrumb trail */}
              <div className="flex items-center gap-1 overflow-x-auto text-xs min-w-0">
                {navHistory.map((h, i) => (
                  <span key={h.id} className="flex items-center gap-1 whitespace-nowrap">
                    {i > 0 && <ChevronRight size={10} className="text-text-tertiary flex-shrink-0" />}
                    <button
                      onClick={() => { navigateToNode(h.id); }}
                      className={`hover:text-accent-gold transition-colors ${
                        h.id === selected.node.id ? "text-accent-gold font-semibold" : "text-text-tertiary"
                      }`}
                    >
                      {h.name.length > 18 ? h.name.slice(0, 16) + "…" : h.name}
                    </button>
                  </span>
                ))}
              </div>
              {/* Font size + close */}
              <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                <button
                  onClick={() => setFontSize(Math.max(0, fontSize - 1))}
                  className={`px-1.5 py-0.5 rounded text-xs transition-colors ${fontSize === 0 ? "text-text-tertiary cursor-default" : "hover:bg-surface-hover text-text-secondary"}`}
                  title={locale === "he" ? "טקסט קטן" : "Smaller text"}
                >
                  A-
                </button>
                <button
                  onClick={() => setFontSize(Math.min(2, fontSize + 1))}
                  className={`px-1.5 py-0.5 rounded text-xs transition-colors ${fontSize === 2 ? "text-text-tertiary cursor-default" : "hover:bg-surface-hover text-text-secondary"}`}
                  title={locale === "he" ? "טקסט גדול" : "Larger text"}
                >
                  A+
                </button>
                <button
                  onClick={() => { selectNode(null); highlightSelection(null); setNavHistory([]); }}
                  className="p-1 rounded hover:bg-surface-hover text-text-secondary"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Selected node header */}
            <div className="px-5 py-4 border-b border-border">
              <div className="flex items-start gap-2.5">
                <span className="w-4 h-4 rounded-full flex-shrink-0 mt-1" style={{ backgroundColor: selected.node.color }} />
                <div className="min-w-0 flex-1">
                  <h3 className="font-bold text-lg text-foreground leading-snug">{selected.node.name}</h3>
                  <div className="flex items-center gap-3 mt-2">
                    <span className={`${subSize} uppercase tracking-wider font-semibold px-2 py-0.5 rounded bg-surface-sunken text-text-secondary`}>
                      {selected.node.type}
                    </span>
                    {selected.node.paper_count ? (
                      <span className={`${subSize} text-text-tertiary`}>
                        {selected.node.paper_count} {t.papers}
                      </span>
                    ) : null}
                    <div className="flex items-center gap-1.5 flex-1">
                      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent-gold rounded-full"
                          style={{ width: `${Math.round(selected.node.confidence * 100)}%` }}
                        />
                      </div>
                      <span className={`${subSize} text-text-tertiary font-mono`}>
                        {Math.round(selected.node.confidence * 100)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Definition / What is this? */}
              {(selected.node.definition || conceptDetail?.definition) && (
                <div className="px-5 py-4 border-b border-border/50">
                  <h4 className={`${subSize} font-semibold text-foreground mb-2`}>
                    {locale === "he" ? "מה זה?" : "What is this?"}
                  </h4>
                  <p className={`${bodySize} text-text-secondary leading-relaxed`}>
                    {conceptDetail?.definition || selected.node.definition}
                  </p>
                </div>
              )}

              {/* Key Papers — educational context */}
              {conceptDetail?.key_papers?.length > 0 && (
                <div className="px-5 py-4 border-b border-border/50">
                  <h4 className={`${subSize} font-semibold text-foreground mb-2 flex items-center gap-2`}>
                    <BookOpen size={14} className="text-accent-blue" />
                    {t.keyPapers}
                  </h4>
                  <div className="space-y-2.5">
                    {conceptDetail.key_papers.map((paper: any) => (
                      <div key={paper.id} className="rounded-lg bg-background/50 px-3 py-2.5">
                        {paper.doi ? (
                          <a
                            href={paper.doi.startsWith("http") ? paper.doi : `https://doi.org/${paper.doi}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`${subSize} text-accent-blue hover:underline leading-snug font-medium block`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {paper.title} ↗
                          </a>
                        ) : (
                          <p className={`${subSize} text-foreground leading-snug font-medium`}>{paper.title}</p>
                        )}
                        <p className="text-xs text-text-tertiary mt-1">
                          {Array.isArray(paper.authors)
                            ? paper.authors.slice(0, 3).map((a: any) => a.name || a).join(", ")
                            : paper.authors || ""}
                          {Array.isArray(paper.authors) && paper.authors.length > 3 ? " et al." : ""}
                          {paper.publication_year ? ` (${paper.publication_year})` : ""}
                          {paper.cited_by_count ? ` · ${paper.cited_by_count} citations` : ""}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Key Claims — what does research say? */}
              {conceptDetail?.key_claims?.length > 0 && (
                <div className="px-5 py-4 border-b border-border/50">
                  <h4 className={`${subSize} font-semibold text-foreground mb-2 flex items-center gap-2`}>
                    <MessageSquare size={14} className="text-accent-amber" />
                    {t.keyClaims}
                  </h4>
                  <div className="space-y-2">
                    {conceptDetail.key_claims.map((claim: any, i: number) => (
                      <div key={i} className="rounded-lg bg-background/50 px-3 py-2.5">
                        <p className={`${subSize} text-text-secondary leading-relaxed`}>
                          &ldquo;{claim.claim_text}&rdquo;
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          {claim.evidence_type && (
                            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-surface-sunken text-text-tertiary">
                              {claim.evidence_type}
                            </span>
                          )}
                          {claim.strength && (
                            <span className="text-[10px] text-text-tertiary">
                              {locale === "he" ? "עוצמה:" : "Strength:"} {claim.strength}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Loading indicator for detail */}
              {loadingDetail && (
                <div className="px-5 py-3 text-xs text-text-tertiary flex items-center gap-2">
                  <div className="w-3 h-3 border border-accent-gold border-t-transparent rounded-full animate-spin" />
                  {locale === "he" ? "טוען מידע נוסף..." : "Loading more details..."}
                </div>
              )}

              {/* No definition? Show helpful fallback */}
              {!selected.node.definition && !conceptDetail?.definition && !loadingDetail && (
                <div className="px-5 py-4 border-b border-border/50">
                  <p className={`${bodySize} text-text-tertiary italic leading-relaxed`}>
                    {locale === "he"
                      ? `"${selected.node.name}" הוא מושג מסוג ${selected.node.type} בגרף הידע. לחץ על מושגים מחוברים כדי להבין את ההקשר שלו.`
                      : `"${selected.node.name}" is a ${selected.node.type} in the knowledge graph. Explore connected concepts below to understand its context.`}
                  </p>
                </div>
              )}

              {/* Connections with explanations */}
              <div className="px-5 py-3">
                <span className={`${subSize} uppercase tracking-wider font-semibold text-text-tertiary`}>
                  {t.connectedConcepts} ({selected.connections.length})
                </span>
              </div>
              {selected.connections.length === 0 ? (
                <div className={`px-5 pb-4 ${bodySize} text-text-tertiary`}>
                  {locale === "he" ? "אין חיבורים ישירים" : "No direct connections"}
                </div>
              ) : (
                <div className="px-3 pb-3 space-y-0.5">
                  {selected.connections.map((conn, i) => (
                    <button
                      key={`${conn.node.id}-${i}`}
                      onClick={() => {
                        navigateToNode(conn.node.id);
                      }}
                      className="w-full px-3 py-2.5 rounded-lg hover:bg-surface-hover transition-colors text-left"
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: conn.node.color }} />
                        <div className="min-w-0 flex-1">
                          <div className={`${subSize} text-foreground leading-snug`}>{conn.node.name}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span
                              className="w-3 h-0.5 rounded flex-shrink-0"
                              style={{ backgroundColor: EDGE_COLORS[conn.edgeType] || "#2D3548" }}
                            />
                            <span className="text-xs text-text-tertiary">
                              {conn.direction === "to"
                                ? (EDGE_LABELS[conn.edgeType]?.[li] || conn.edgeType.toLowerCase())
                                : (locale === "he" ? "מ: " : "from: ") + (EDGE_LABELS[conn.edgeType]?.[li] || conn.edgeType.toLowerCase())
                              }
                            </span>
                          </div>
                        </div>
                        <span className="text-xs text-text-tertiary font-mono flex-shrink-0">
                          {Math.round(conn.node.confidence * 100)}%
                        </span>
                      </div>
                      {/* Connection explanation — WHY these are connected */}
                      {conn.explanation && (
                        <p className={`${subSize} text-text-tertiary leading-relaxed mt-1.5 ml-5 italic`}>
                          {conn.explanation}
                        </p>
                      )}
                      {/* Source paper that established this connection */}
                      {conn.source_paper && (
                        <p className="text-xs text-accent-gold/60 mt-1 ml-5 leading-snug">
                          {locale === "he" ? "מקור: " : "Source: "}{conn.source_paper}
                        </p>
                      )}
                      {/* Agree/Disagree feedback */}
                      <div className="ml-5 mt-1">
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
