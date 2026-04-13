"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface GraphNode {
  id: string;
  name: string;
  type?: string;
  paper_count?: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  tier: number; // 0=foundation, 1=core, 2=intermediate, 3=advanced
}

interface GraphEdge {
  source: string;
  target: string;
  type?: string;
}

interface ConceptGraphProps {
  field: string;
  onSelectConcept: (id: string) => void;
  selectedConceptId?: string | null;
}

const TIER_COLORS = [
  "#E8B931", // foundation — gold
  "#58A6FF", // core — blue
  "#3FB950", // intermediate — green
  "#BC8CFF", // advanced — purple
];

const TIER_LABELS = ["Foundation", "Core", "Intermediate", "Advanced"];

export default function ConceptGraph({ field, onSelectConcept, selectedConceptId }: ConceptGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);
  const animRef = useRef<number>(0);
  const dragRef = useRef<{ node: GraphNode | null; offsetX: number; offsetY: number }>({ node: null, offsetX: 0, offsetY: 0 });
  const hoveredRef = useRef<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodeCount, setNodeCount] = useState(0);
  const { locale } = useLocaleStore();

  // Fetch graph data
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Get concepts
        const res = await fetch(`${API_BASE}/features/fields/${encodeURIComponent(field)}/concepts?limit=80`);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        const concepts = data.concepts || [];

        if (!concepts.length || cancelled) {
          setLoading(false);
          return;
        }

        // Get graph edges (relationships)
        let edges: GraphEdge[] = [];
        try {
          const gRes = await fetch(`${API_BASE}/features/visualization/graph?limit=80`);
          if (gRes.ok) {
            const gData = await gRes.json();
            const conceptIds = new Set(concepts.map((c: any) => c.id));
            edges = (gData.edges || [])
              .filter((e: any) => conceptIds.has(e.source) && conceptIds.has(e.target))
              .map((e: any) => ({ source: e.source, target: e.target, type: e.type }));
          }
        } catch { /* edges are optional */ }

        // Sort by paper_count for tier assignment
        const sorted = [...concepts].sort((a: any, b: any) => (b.paper_count || 0) - (a.paper_count || 0));
        const total = sorted.length;
        const tierCuts = [Math.floor(total * 0.15), Math.floor(total * 0.4), Math.floor(total * 0.7), total];

        // Create nodes with initial positions (circular by tier)
        const canvas = canvasRef.current;
        const w = canvas?.width || 600;
        const h = canvas?.height || 500;
        const cx = w / 2;
        const cy = h / 2;

        const nodes: GraphNode[] = sorted.map((c: any, i: number) => {
          const tier = i < tierCuts[0] ? 0 : i < tierCuts[1] ? 1 : i < tierCuts[2] ? 2 : 3;
          const tierRadius = 60 + tier * 70;
          const tierStart = tier === 0 ? 0 : tierCuts[tier - 1];
          const tierCount = tierCuts[tier] - tierStart;
          const angle = ((i - tierStart) / Math.max(tierCount, 1)) * Math.PI * 2 - Math.PI / 2;

          return {
            id: c.id,
            name: c.name,
            type: c.type,
            paper_count: c.paper_count || 0,
            x: cx + Math.cos(angle) * tierRadius + (Math.random() - 0.5) * 20,
            y: cy + Math.sin(angle) * tierRadius + (Math.random() - 0.5) * 20,
            vx: 0,
            vy: 0,
            tier,
          };
        });

        if (!cancelled) {
          nodesRef.current = nodes;
          edgesRef.current = edges;
          setNodeCount(nodes.length);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [field]);

  // Resize canvas
  useEffect(() => {
    const resize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (canvas && container) {
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
      }
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // Force simulation + render loop
  useEffect(() => {
    if (loading) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let running = true;
    let cooldown = 300; // simulation steps

    const nodeMap = new Map(nodesRef.current.map(n => [n.id, n]));

    const tick = () => {
      if (!running) return;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;
      const w = canvas.width;
      const h = canvas.height;

      if (cooldown > 0) {
        cooldown--;
        const alpha = Math.max(0.01, cooldown / 300 * 0.3);

        // Repulsion (all pairs)
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            let dx = b.x - a.x;
            let dy = b.y - a.y;
            const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
            const force = 800 / (dist * dist);
            const fx = (dx / dist) * force * alpha;
            const fy = (dy / dist) * force * alpha;
            a.vx -= fx; a.vy -= fy;
            b.vx += fx; b.vy += fy;
          }
        }

        // Attraction (edges)
        for (const edge of edges) {
          const a = nodeMap.get(edge.source);
          const b = nodeMap.get(edge.target);
          if (!a || !b) continue;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const force = (dist - 100) * 0.005 * alpha;
          const fx = (dx / Math.max(dist, 1)) * force;
          const fy = (dy / Math.max(dist, 1)) * force;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }

        // Apply velocity + damping
        for (const node of nodes) {
          if (dragRef.current.node === node) continue;
          node.vx *= 0.85;
          node.vy *= 0.85;
          node.x += node.vx;
          node.y += node.vy;
          // Bounds
          node.x = Math.max(30, Math.min(w - 30, node.x));
          node.y = Math.max(30, Math.min(h - 30, node.y));
        }
      }

      // Render
      ctx.clearRect(0, 0, w, h);

      // Edges
      ctx.lineWidth = 0.5;
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      for (const edge of edges) {
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // Hovered node's edges highlighted
      const hovered = hoveredRef.current;
      if (hovered) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "rgba(232,185,49,0.4)";
        for (const edge of edges) {
          if (edge.source === hovered.id || edge.target === hovered.id) {
            const a = nodeMap.get(edge.source);
            const b = nodeMap.get(edge.target);
            if (a && b) {
              ctx.beginPath();
              ctx.moveTo(a.x, a.y);
              ctx.lineTo(b.x, b.y);
              ctx.stroke();
            }
          }
        }
      }

      // Nodes
      for (const node of nodes) {
        const isSelected = node.id === selectedConceptId;
        const isHovered = hovered?.id === node.id;
        const radius = Math.max(4, Math.min(12, 3 + (node.paper_count || 0) * 0.3));
        const color = TIER_COLORS[node.tier] || "#8B949E";

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? "#E8B931" : isHovered ? "#fff" : color;
        ctx.globalAlpha = isSelected || isHovered ? 1 : 0.7;
        ctx.fill();
        ctx.globalAlpha = 1;

        if (isSelected || isHovered) {
          ctx.strokeStyle = "#E8B931";
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Label
        if (isHovered || isSelected || radius > 7) {
          ctx.font = `${isHovered || isSelected ? "bold " : ""}${isHovered || isSelected ? 12 : 10}px system-ui, sans-serif`;
          ctx.fillStyle = isHovered || isSelected ? "#fff" : "rgba(255,255,255,0.6)";
          ctx.textAlign = "center";
          const label = node.name.length > 25 ? node.name.slice(0, 22) + "..." : node.name;
          ctx.fillText(label, node.x, node.y - radius - 4);
        }
      }

      // Legend
      ctx.font = "10px system-ui, sans-serif";
      for (let i = 0; i < 4; i++) {
        const lx = 12;
        const ly = h - 60 + i * 15;
        ctx.fillStyle = TIER_COLORS[i];
        ctx.beginPath();
        ctx.arc(lx, ly, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.5)";
        ctx.textAlign = "left";
        ctx.fillText(TIER_LABELS[i], lx + 10, ly + 3);
      }

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);

    return () => {
      running = false;
      cancelAnimationFrame(animRef.current);
    };
  }, [loading, selectedConceptId]);

  // Mouse interactions
  const getNodeAt = useCallback((mx: number, my: number): GraphNode | null => {
    for (const node of nodesRef.current) {
      const r = Math.max(6, Math.min(14, 3 + (node.paper_count || 0) * 0.3));
      const dx = mx - node.x;
      const dy = my - node.y;
      if (dx * dx + dy * dy < (r + 4) * (r + 4)) return node;
    }
    return null;
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const node = getNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (node) {
      dragRef.current = { node, offsetX: e.clientX - node.x, offsetY: e.clientY - node.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (dragRef.current.node) {
      dragRef.current.node.x = e.clientX - dragRef.current.offsetX;
      dragRef.current.node.y = e.clientY - dragRef.current.offsetY;
      return;
    }

    const node = getNodeAt(mx, my);
    hoveredRef.current = node;
    const canvas = canvasRef.current;
    if (canvas) canvas.style.cursor = node ? "pointer" : "default";
  };

  const handleMouseUp = () => {
    const dragged = dragRef.current.node;
    dragRef.current = { node: null, offsetX: 0, offsetY: 0 };
    // If barely moved, treat as click
  };

  const handleClick = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const node = getNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (node) onSelectConcept(node.id);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        Loading graph...
      </div>
    );
  }

  if (nodeCount === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm px-4 text-center">
        No concepts available yet
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full w-full relative overflow-hidden bg-background">
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onClick={handleClick}
        className="w-full h-full"
      />
      <div className="absolute top-2 left-3 text-[10px] text-text-tertiary">
        {nodeCount} concepts — drag to explore, click to learn
      </div>
    </div>
  );
}
