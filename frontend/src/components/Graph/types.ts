import * as d3 from "d3";

// --- Node & Edge data ---

export interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  type: string;
  confidence: number;
  color: string;
  definition?: string;
  paper_count?: number;
  // Lens metadata (optional, fetched when lens is active)
  controversy_score?: number;
  max_publication_year?: number;
  community_activity?: number;
  connection_count?: number;
}

export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  confidence: number;
  explanation?: string;
  source_paper?: string;
  // Lens metadata
  disagree_count?: number;
}

export interface SelectedInfo {
  node: GraphNode;
  connections: ConnectionInfo[];
}

export interface ConnectionInfo {
  node: GraphNode;
  edgeId: string;
  edgeType: string;
  direction: "to" | "from";
  explanation?: string;
  source_paper?: string;
}

// --- View system ---

export type ViewType = "force" | "hierarchical" | "radial" | "geographic" | "sankey";
export type LensType = "none" | "controversy" | "recency" | "confidence" | "community" | "gap";

export interface ViewOptions {
  width: number;
  height: number;
  hiddenTypes: Set<string>;
  showAllLabels: boolean;
  rootNodeId?: string;
  onNodeClick: (nodeId: string) => void;
  onBackgroundClick: () => void;
}

export interface ViewCleanup {
  simulation?: d3.Simulation<GraphNode, GraphEdge>;
  zoom?: d3.ZoomBehavior<SVGSVGElement, unknown>;
  navigateToNode?: (nodeId: string) => void;
}

export type ViewRenderer = (
  svg: SVGSVGElement,
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: ViewOptions
) => ViewCleanup;

// --- Lens system ---

export interface NodeOverride {
  opacity?: number;
  radius?: number;
  stroke?: string;
  strokeWidth?: number;
  filter?: string; // SVG filter id for glow etc.
}

export interface EdgeOverride {
  opacity?: number;
  stroke?: string;
  strokeWidth?: number;
  strokeDasharray?: string;
}

export interface LensData {
  nodeOverrides: Map<string, NodeOverride>;
  edgeOverrides: Map<string, EdgeOverride>;
  extraElements?: ExtraLensElement[];
}

export interface ExtraLensElement {
  type: "line";
  sourceId: string;
  targetId: string;
  stroke: string;
  strokeDasharray: string;
  opacity: number;
}

// --- Graph settings (user-controlled filters) ---

export interface GraphSettings {
  minConnections: number;
  minConfidence: number;
  minPapers: number;
  hiddenEdgeTypes: Set<string>;
  yearRange: [number, number]; // [min, max]
}

export const DEFAULT_GRAPH_SETTINGS: GraphSettings = {
  minConnections: 0,
  minConfidence: 0,
  minPapers: 0,
  hiddenEdgeTypes: new Set(),
  yearRange: [1900, 2030],
};

// --- Constants ---

export const EDGE_COLORS: Record<string, string> = {
  RELATES_TO: "#2D3548",
  CONTRADICTS: "#F85149",
  SUPPORTS: "#3FB950",
  BUILDS_ON: "#58A6FF",
  RESPONDS_TO: "#D29922",
};

export const EDGE_LABELS: Record<string, [string, string]> = {
  RELATES_TO: ["relates to", "קשור ל"],
  CONTRADICTS: ["contradicts", "סותר"],
  SUPPORTS: ["supports", "תומך ב"],
  BUILDS_ON: ["builds on", "מבוסס על"],
  RESPONDS_TO: ["responds to", "מגיב ל"],
};

export const NODE_TYPES: { type: string; label: [string, string]; color: string }[] = [
  { type: "theory", label: ["Theory", "תאוריה"], color: "#E8B931" },
  { type: "method", label: ["Method", "שיטה"], color: "#58A6FF" },
  { type: "framework", label: ["Framework", "מסגרת"], color: "#3FB950" },
  { type: "phenomenon", label: ["Phenomenon", "תופעה"], color: "#D29922" },
  { type: "paradigm", label: ["Paradigm", "פרדיגמה"], color: "#E8B931" },
  { type: "critique", label: ["Critique", "ביקורת"], color: "#F85149" },
  { type: "tool", label: ["Tool", "כלי"], color: "#BC8CFF" },
  { type: "metric", label: ["Metric", "מדד"], color: "#F78166" },
];

export const ALL_EDGE_TYPES = Object.keys(EDGE_COLORS);
