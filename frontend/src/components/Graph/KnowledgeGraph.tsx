"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import {
  X, ZoomIn, ZoomOut, Maximize2, Search, ChevronRight, BookOpen, MessageSquare,
  Filter, Network, GitBranch, Target, Globe2, BarChart3, SlidersHorizontal, Eye,
} from "lucide-react";
import { getConceptDetail } from "@/lib/api";
import ConnectionFeedback from "./ConnectionFeedback";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";
import { useGraphData } from "./hooks/useGraphData";
import renderForceView from "./views/ForceView";
import renderHierarchicalView from "./views/HierarchicalView";
import renderRadialView from "./views/RadialView";
import renderGeographicView from "./views/GeographicView";
import renderSankeyView from "./views/SankeyView";
import { computeLens, applyLensToSvg } from "./lenses/lensEngine";
import type {
  GraphNode, GraphEdge, SelectedInfo, ViewType, LensType, ViewCleanup,
  GraphSettings, ConnectionInfo,
} from "./types";
import {
  EDGE_COLORS, EDGE_LABELS, NODE_TYPES, ALL_EDGE_TYPES, DEFAULT_GRAPH_SETTINGS,
} from "./types";

interface KnowledgeGraphProps {
  onClose: () => void;
}

// --- View metadata ---
const VIEWS: { type: ViewType; icon: typeof Network; label: [string, string]; ready: boolean }[] = [
  { type: "force", icon: Network, label: ["Force", "כוחות"], ready: true },
  { type: "hierarchical", icon: GitBranch, label: ["Hierarchy", "היררכיה"], ready: true },
  { type: "radial", icon: Target, label: ["Radial", "רדיאלי"], ready: true },
  { type: "geographic", icon: Globe2, label: ["Geographic", "גיאוגרפי"], ready: true },
  { type: "sankey", icon: BarChart3, label: ["Sankey", "זרימה"], ready: true },
];

// --- Lens metadata ---
const LENSES: { type: LensType; label: [string, string]; color: string; desc: [string, string] }[] = [
  { type: "none", label: ["None", "ללא"], color: "#8B949E", desc: ["Default view", "תצוגה רגילה"] },
  { type: "controversy", label: ["Controversy", "מחלוקת"], color: "#F85149", desc: ["Highlight disputed connections", "הדגש חיבורים שנויים במחלוקת"] },
  { type: "recency", label: ["Recency", "עדכניות"], color: "#58A6FF", desc: ["Fade old, brighten new", "דעך ישנים, הבהר חדשים"] },
  { type: "confidence", label: ["Confidence", "ביטחון"], color: "#E8B931", desc: ["Size by establishment level", "גודל לפי רמת ביסוס"] },
  { type: "community", label: ["Community", "קהילה"], color: "#3FB950", desc: ["Glow by discussion activity", "זוהר לפי פעילות קהילתית"] },
  { type: "gap", label: ["Gaps", "פערים"], color: "#BC8CFF", desc: ["Highlight research opportunities", "הדגש הזדמנויות מחקר"] },
];

export default function KnowledgeGraph({ onClose }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selected, setSelected] = useState<SelectedInfo | null>(null);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GraphNode[]>([]);
  const [fontSize, setFontSize] = useState(1);
  const [conceptDetail, setConceptDetail] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [navHistory, setNavHistory] = useState<{ id: string; name: string }[]>([]);
  const [activeView, setActiveView] = useState<ViewType>("force");
  const [activeLens, setActiveLens] = useState<LensType>("none");
  const [showLenses, setShowLenses] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<GraphSettings>({ ...DEFAULT_GRAPH_SETTINGS });

  const { graphData, loading } = useGraphData(150, activeLens);

  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const setConceptPanelOpen = useChatStore((s) => s.setConceptPanelOpen);
  const { locale, t } = useLocaleStore();

  const viewCleanupRef = useRef<ViewCleanup | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);

  const li = locale === "he" ? 1 : 0;
  const textSizes = ["text-sm", "text-[15px]", "text-lg"];
  const bodySize = textSizes[fontSize];
  const subSize = ["text-xs", "text-sm", "text-[15px]"][fontSize];

  // --- Apply graph settings to filter nodes/edges ---
  const getFilteredData = useCallback(() => {
    if (!graphData) return { nodes: [], edges: [] };
    let nodes = graphData.nodes;
    let edges = graphData.edges;

    // Filter nodes
    nodes = nodes.filter((n) => {
      if (hiddenTypes.has(n.type)) return false;
      if ((n.connection_count || 0) < settings.minConnections) return false;
      if (n.confidence < settings.minConfidence) return false;
      if ((n.paper_count || 0) < settings.minPapers) return false;
      return true;
    });

    const visibleIds = new Set(nodes.map((n) => n.id));

    // Filter edges
    edges = edges.filter((e) => {
      const src = typeof e.source === "string" ? e.source : e.source.id;
      const tgt = typeof e.target === "string" ? e.target : e.target.id;
      if (!visibleIds.has(src) || !visibleIds.has(tgt)) return false;
      if (settings.hiddenEdgeTypes.has(e.type)) return false;
      return true;
    });

    return { nodes, edges };
  }, [graphData, hiddenTypes, settings]);

  // --- Node selection ---
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

    const connections: ConnectionInfo[] = [];
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

    if (addToHistory) {
      setNavHistory((prev) => {
        const already = prev.findIndex((h) => h.id === nodeId);
        if (already >= 0) return prev.slice(0, already + 1);
        return [...prev.slice(-4), { id: nodeId, name: node.name }];
      });
    }

    setLoadingDetail(true);
    setConceptDetail(null);
    getConceptDetail(nodeId)
      .then((detail) => setConceptDetail(detail))
      .catch(() => setConceptDetail(null))
      .finally(() => setLoadingDetail(false));
  }, []);

  // --- Highlight selection in SVG ---
  const highlightSelection = useCallback((nodeId: string | null) => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);

    if (!nodeId) {
      svg.selectAll<SVGCircleElement, GraphNode>("circle.graph-node")
        .attr("opacity", 1).attr("stroke", "#0C0F14").attr("stroke-width", 1);
      svg.selectAll<SVGLineElement, GraphEdge>("line.graph-edge")
        .attr("stroke-opacity", 0.4).attr("stroke-width", (d) => Math.max(0.5, d.confidence * 2));
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

    svg.selectAll<SVGCircleElement, GraphNode>("circle.graph-node")
      .attr("opacity", (d) => connectedIds.has(d.id) ? 1 : 0.15)
      .attr("stroke", (d) => connectedIds.has(d.id) ? "#E8B931" : "#0C0F14")
      .attr("stroke-width", (d) => d.id === nodeId ? 3 : connectedIds.has(d.id) ? 1.5 : 1);

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

    svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
      .attr("opacity", (d) => connectedIds.has(d.id) ? 1 : 0.1);
  }, []);

  // --- Render active view ---
  useEffect(() => {
    if (!svgRef.current || !graphData) return;

    const { nodes, edges } = getFilteredData();
    // Clone nodes to avoid mutation across re-renders
    const clonedNodes = nodes.map((n) => ({ ...n }));
    const clonedEdges = edges.map((e) => ({ ...e }));
    nodesRef.current = clonedNodes;
    edgesRef.current = clonedEdges;

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    const options = {
      width,
      height,
      hiddenTypes,
      showAllLabels,
      rootNodeId: selected?.node.id,
      onNodeClick: (nodeId: string) => {
        selectNode(nodeId);
        highlightSelection(nodeId);
      },
      onBackgroundClick: () => {
        selectNode(null);
        highlightSelection(null);
      },
    };

    // Stop previous simulation
    viewCleanupRef.current?.simulation?.stop();

    // Render the active view
    let cleanup: ViewCleanup;
    switch (activeView) {
      case "hierarchical":
        cleanup = renderHierarchicalView(svgRef.current, clonedNodes, clonedEdges, options);
        break;
      case "radial":
        cleanup = renderRadialView(svgRef.current, clonedNodes, clonedEdges, options);
        break;
      case "geographic":
        cleanup = renderGeographicView(svgRef.current, clonedNodes, clonedEdges, options);
        break;
      case "sankey":
        cleanup = renderSankeyView(svgRef.current, clonedNodes, clonedEdges, options);
        break;
      case "force":
      default:
        cleanup = renderForceView(svgRef.current, clonedNodes, clonedEdges, options);
        break;
    }

    viewCleanupRef.current = cleanup;

    // Apply lens overrides after view renders
    if (activeLens !== "none" && svgRef.current) {
      // Small delay to let D3 finish initial tick
      const lensTimer = setTimeout(() => {
        if (!svgRef.current) return;
        const lensData = computeLens(activeLens, clonedNodes, clonedEdges);
        applyLensToSvg(svgRef.current, lensData);
      }, 300);
      return () => {
        cleanup.simulation?.stop();
        clearTimeout(lensTimer);
      };
    }

    return () => {
      cleanup.simulation?.stop();
    };
  }, [graphData, activeView, activeLens, getFilteredData, hiddenTypes, showAllLabels, selectNode, highlightSelection]);

  // --- Label toggle ---
  useEffect(() => {
    if (!svgRef.current || selected) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll<SVGTextElement, GraphNode>("text.graph-label")
      .attr("opacity", (d) => showAllLabels || d.confidence > 0.7 ? 1 : 0);
  }, [showAllLabels, selected]);

  // --- Zoom helpers ---
  const handleZoom = (factor: number) => {
    if (!svgRef.current || !viewCleanupRef.current?.zoom) return;
    const svg = d3.select(svgRef.current);
    svg.transition().duration(300).call(viewCleanupRef.current.zoom.scaleBy, factor);
  };

  const handleFit = () => {
    if (!svgRef.current || !viewCleanupRef.current?.zoom) return;
    const svg = d3.select(svgRef.current);
    svg.transition().duration(500).call(
      viewCleanupRef.current.zoom.transform,
      d3.zoomIdentity.translate(svgRef.current.clientWidth / 2, svgRef.current.clientHeight / 2).scale(0.8)
    );
  };

  // --- Search ---
  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (query.length < 2) { setSearchResults([]); return; }
    const q = query.toLowerCase();
    const results = nodesRef.current
      .filter((n) => n.name.toLowerCase().includes(q))
      .sort((a, b) => b.confidence - a.confidence)
      .slice(0, 8);
    setSearchResults(results);
  };

  const navigateToNode = (nodeId: string) => {
    viewCleanupRef.current?.navigateToNode?.(nodeId);
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

  const filteredData = getFilteredData();
  const nodeCount = filteredData.nodes.length;
  const edgeCount = filteredData.edges.length;
  const totalNodes = graphData?.nodeCount || 0;
  const isFiltered = nodeCount < totalNodes;

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* ===== HEADER ===== */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-foreground">{t.knowledgeMap}</h2>
          <span className="text-xs text-text-secondary">
            {nodeCount} {locale === "he" ? "צמתים" : "nodes"} &middot; {edgeCount} {locale === "he" ? "קשרים" : "edges"}
            {isFiltered && (
              <span className="text-accent-gold ml-1">
                ({locale === "he" ? `מתוך ${totalNodes}` : `of ${totalNodes}`})
              </span>
            )}
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

          {/* View switcher */}
          <div className="flex items-center bg-surface-sunken rounded-lg p-0.5 gap-0.5">
            {VIEWS.map((v) => {
              const Icon = v.icon;
              return (
                <button
                  key={v.type}
                  onClick={() => v.ready && setActiveView(v.type)}
                  disabled={!v.ready}
                  title={v.label[li] + (!v.ready ? (locale === "he" ? " (בקרוב)" : " (coming soon)") : "")}
                  className={`p-1.5 rounded transition-colors ${
                    activeView === v.type
                      ? "bg-accent-gold/15 text-accent-gold"
                      : v.ready
                        ? "hover:bg-surface-hover text-text-secondary"
                        : "text-text-tertiary opacity-40 cursor-not-allowed"
                  }`}
                >
                  <Icon size={14} />
                </button>
              );
            })}
          </div>

          {/* Toggles */}
          <button
            onClick={() => setShowAllLabels(!showAllLabels)}
            className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              showAllLabels ? "bg-accent-gold/15 text-accent-gold" : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            {locale === "he" ? "תוויות" : "Labels"}
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              showFilters || hiddenTypes.size > 0 ? "bg-accent-gold/15 text-accent-gold" : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            <Filter size={12} />
            {locale === "he" ? "סינון" : "Filter"}
            {hiddenTypes.size > 0 && (
              <span className="ml-0.5 px-1 py-px rounded-full bg-accent-gold/20 text-[9px]">{hiddenTypes.size}</span>
            )}
          </button>
          <button
            onClick={() => setShowLenses(!showLenses)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              activeLens !== "none" ? "bg-accent-gold/15 text-accent-gold" : showLenses ? "bg-surface-hover text-text-secondary" : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            <Eye size={12} />
            {locale === "he" ? "עדשות" : "Lenses"}
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              showSettings ? "bg-accent-gold/15 text-accent-gold" : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            <SlidersHorizontal size={12} />
            {locale === "he" ? "הגדרות" : "Settings"}
          </button>

          {/* Zoom controls */}
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

      {/* ===== TYPE FILTER BAR ===== */}
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
                  isHidden ? "opacity-40 bg-surface-sunken text-text-tertiary line-through" : "bg-surface-hover text-foreground"
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

      {/* ===== LENS SELECTOR ===== */}
      {showLenses && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-border bg-surface/50">
          <span className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mr-1">
            {locale === "he" ? "עדשה:" : "Lens:"}
          </span>
          {LENSES.map((lens) => (
            <button
              key={lens.type}
              onClick={() => setActiveLens(activeLens === lens.type ? "none" : lens.type)}
              title={lens.desc[li]}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                activeLens === lens.type
                  ? "text-white"
                  : "bg-surface-hover text-text-secondary hover:text-foreground"
              }`}
              style={activeLens === lens.type ? { backgroundColor: lens.color + "30", color: lens.color } : {}}
            >
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: lens.color }} />
              {lens.label[li]}
            </button>
          ))}
        </div>
      )}

      {/* ===== GRAPH SETTINGS PANEL ===== */}
      {showSettings && (
        <div className="px-4 py-3 border-b border-border bg-surface/50 space-y-3">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Min connections */}
            <div>
              <label className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold block mb-1">
                {locale === "he" ? "מינימום חיבורים" : "Min connections"}
                <span className="text-accent-gold ml-1">{settings.minConnections}</span>
              </label>
              <input
                type="range" min={0} max={20} step={1}
                value={settings.minConnections}
                onChange={(e) => setSettings((s) => ({ ...s, minConnections: +e.target.value }))}
                className="w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer accent-accent-gold"
              />
            </div>
            {/* Min confidence */}
            <div>
              <label className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold block mb-1">
                {locale === "he" ? "מינימום ביטחון" : "Min confidence"}
                <span className="text-accent-gold ml-1">{Math.round(settings.minConfidence * 100)}%</span>
              </label>
              <input
                type="range" min={0} max={1} step={0.05}
                value={settings.minConfidence}
                onChange={(e) => setSettings((s) => ({ ...s, minConfidence: +e.target.value }))}
                className="w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer accent-accent-gold"
              />
            </div>
            {/* Min papers */}
            <div>
              <label className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold block mb-1">
                {locale === "he" ? "מינימום מאמרים" : "Min papers"}
                <span className="text-accent-gold ml-1">{settings.minPapers}</span>
              </label>
              <input
                type="range" min={0} max={50} step={1}
                value={settings.minPapers}
                onChange={(e) => setSettings((s) => ({ ...s, minPapers: +e.target.value }))}
                className="w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer accent-accent-gold"
              />
            </div>
            {/* Year range */}
            <div>
              <label className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold block mb-1">
                {locale === "he" ? "טווח שנים" : "Year range"}
                <span className="text-accent-gold ml-1">{settings.yearRange[0]}–{settings.yearRange[1]}</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number" min={1900} max={2030}
                  value={settings.yearRange[0]}
                  onChange={(e) => setSettings((s) => ({ ...s, yearRange: [+e.target.value, s.yearRange[1]] }))}
                  className="w-16 px-1.5 py-0.5 bg-surface-sunken border border-border rounded text-xs text-foreground text-center"
                />
                <span className="text-text-tertiary text-xs">–</span>
                <input
                  type="number" min={1900} max={2030}
                  value={settings.yearRange[1]}
                  onChange={(e) => setSettings((s) => ({ ...s, yearRange: [s.yearRange[0], +e.target.value] }))}
                  className="w-16 px-1.5 py-0.5 bg-surface-sunken border border-border rounded text-xs text-foreground text-center"
                />
              </div>
            </div>
          </div>

          {/* Edge type toggles */}
          <div>
            <span className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold block mb-1.5">
              {locale === "he" ? "סוגי קשרים:" : "Edge types:"}
            </span>
            <div className="flex flex-wrap gap-2">
              {ALL_EDGE_TYPES.map((edgeType) => {
                const isHidden = settings.hiddenEdgeTypes.has(edgeType);
                return (
                  <button
                    key={edgeType}
                    onClick={() => {
                      setSettings((s) => {
                        const next = new Set(s.hiddenEdgeTypes);
                        if (next.has(edgeType)) next.delete(edgeType);
                        else next.add(edgeType);
                        return { ...s, hiddenEdgeTypes: next };
                      });
                    }}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                      isHidden ? "opacity-40 bg-surface-sunken text-text-tertiary line-through" : "bg-surface-hover text-foreground"
                    }`}
                  >
                    <span className="w-3 h-0.5 rounded flex-shrink-0" style={{ backgroundColor: isHidden ? "#3A3F47" : EDGE_COLORS[edgeType] }} />
                    {EDGE_LABELS[edgeType]?.[li] || edgeType.toLowerCase()}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Reset button */}
          <button
            onClick={() => setSettings({ ...DEFAULT_GRAPH_SETTINGS })}
            className="text-[10px] font-medium text-accent-gold hover:text-accent-gold/80 transition-colors"
          >
            {locale === "he" ? "אפס הגדרות" : "Reset settings"}
          </button>
        </div>
      )}

      {/* ===== EDGE LEGEND ===== */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 border-b border-border text-[10px] text-text-secondary">
        {Object.entries(EDGE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <span className="w-3 h-0.5 rounded" style={{ backgroundColor: color }} />
            <span>{EDGE_LABELS[type]?.[li] || type.toLowerCase()}</span>
          </div>
        ))}
      </div>

      {/* ===== GRAPH + INFO PANEL ===== */}
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

        {/* ===== INFO PANEL ===== */}
        {selected && (
          <div
            className={`absolute top-4 z-20 w-[34rem] max-h-[90%] bg-surface border border-border rounded-xl shadow-lg overflow-hidden flex flex-col ${
              locale === "he" ? "right-4" : "left-4"
            }`}
            dir={locale === "he" ? "rtl" : "ltr"}
          >
            {/* Navigation breadcrumb + controls */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-border/50 bg-surface-sunken/50">
              <div className="flex items-center gap-1 overflow-x-auto text-xs min-w-0">
                {navHistory.map((h, i) => (
                  <span key={h.id} className="flex items-center gap-1 whitespace-nowrap">
                    {i > 0 && <ChevronRight size={10} className="text-text-tertiary flex-shrink-0" />}
                    <button
                      onClick={() => navigateToNode(h.id)}
                      className={`hover:text-accent-gold transition-colors ${
                        h.id === selected.node.id ? "text-accent-gold font-semibold" : "text-text-tertiary"
                      }`}
                    >
                      {h.name.length > 18 ? h.name.slice(0, 16) + "..." : h.name}
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                <button
                  onClick={() => setFontSize(Math.max(0, fontSize - 1))}
                  className={`px-1.5 py-0.5 rounded text-xs transition-colors ${fontSize === 0 ? "text-text-tertiary cursor-default" : "hover:bg-surface-hover text-text-secondary"}`}
                >A-</button>
                <button
                  onClick={() => setFontSize(Math.min(2, fontSize + 1))}
                  className={`px-1.5 py-0.5 rounded text-xs transition-colors ${fontSize === 2 ? "text-text-tertiary cursor-default" : "hover:bg-surface-hover text-text-secondary"}`}
                >A+</button>
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
                        <div className="h-full bg-accent-gold rounded-full" style={{ width: `${Math.round(selected.node.confidence * 100)}%` }} />
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
              {/* Definition */}
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

              {/* Key Papers */}
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

              {/* Key Claims */}
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

              {/* Loading detail */}
              {loadingDetail && (
                <div className="px-5 py-3 text-xs text-text-tertiary flex items-center gap-2">
                  <div className="w-3 h-3 border border-accent-gold border-t-transparent rounded-full animate-spin" />
                  {locale === "he" ? "טוען מידע נוסף..." : "Loading more details..."}
                </div>
              )}

              {/* No definition fallback */}
              {!selected.node.definition && !conceptDetail?.definition && !loadingDetail && (
                <div className="px-5 py-4 border-b border-border/50">
                  <p className={`${bodySize} text-text-tertiary italic leading-relaxed`}>
                    {locale === "he"
                      ? `"${selected.node.name}" הוא מושג מסוג ${selected.node.type} בגרף הידע. לחץ על מושגים מחוברים כדי להבין את ההקשר שלו.`
                      : `"${selected.node.name}" is a ${selected.node.type} in the knowledge graph. Explore connected concepts below to understand its context.`}
                  </p>
                </div>
              )}

              {/* Connections */}
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
                      onClick={() => navigateToNode(conn.node.id)}
                      className="w-full px-3 py-2.5 rounded-lg hover:bg-surface-hover transition-colors text-left"
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: conn.node.color }} />
                        <div className="min-w-0 flex-1">
                          <div className={`${subSize} text-foreground leading-snug`}>{conn.node.name}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="w-3 h-0.5 rounded flex-shrink-0" style={{ backgroundColor: EDGE_COLORS[conn.edgeType] || "#2D3548" }} />
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
                      {conn.explanation && (
                        <p className={`${subSize} text-text-tertiary leading-relaxed mt-1.5 ml-5 italic`}>
                          {conn.explanation}
                        </p>
                      )}
                      {conn.source_paper && (
                        <p className="text-xs text-accent-gold/60 mt-1 ml-5 leading-snug">
                          {locale === "he" ? "מקור: " : "Source: "}{conn.source_paper}
                        </p>
                      )}
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
