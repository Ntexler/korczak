"use client";

/**
 * AtlasView — one continuous knowledge universe.
 *
 * Fields are gravitational REGIONS on a single map, not separate pages.
 * Border concepts (papers spanning 2+ fields) physically sit on the seams.
 * Fog of war covers the whole universe. A minimap + journey trail mean
 * you always know where you are — and how you got there.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { X, Compass, MapPin, BookOpen, Route } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useAtlasStore } from "@/stores/atlasStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface AtlasNode {
  id: string;
  name: string;
  type?: string;
  paper_count: number;
  consensus_status?: string;
  field_span?: string[];
  is_border?: boolean;
  fog?: string | null;
  x: number; y: number; vx: number; vy: number;
}

interface AtlasEdge { source_id: string; target_id: string; relationship_type: string }

interface AtlasViewProps {
  userId?: string;
  onOpenConcept?: (field: string, conceptId: string) => void;
  onSend?: (text: string) => void;
}

// Consensus → node color (the trust map IS the interface)
const CONSENSUS_COLORS: Record<string, string> = {
  consensus: "#E8B931",   // gold — agreed knowledge
  contested: "#F0883E",   // ember — live debate
  emerging: "#58A6FF",    // blue — forming
  unverified: "#6E7681",  // gray — no academic base yet
};

const FIELD_HUES = [45, 200, 280, 150, 0, 320, 100, 25, 240, 175, 60, 300];

function fieldColor(field: string, alpha = 1): string {
  let h = 0;
  for (let i = 0; i < field.length; i++) h = (h * 31 + field.charCodeAt(i)) >>> 0;
  const hue = FIELD_HUES[h % FIELD_HUES.length];
  return `hsla(${hue}, 65%, 55%, ${alpha})`;
}

export default function AtlasView({ userId, onOpenConcept, onSend }: AtlasViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const minimapRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nodesRef = useRef<AtlasNode[]>([]);
  const edgesRef = useRef<AtlasEdge[]>([]);
  const centroidsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const cameraRef = useRef({ x: 0, y: 0, scale: 1 });
  const dragRef = useRef<{ mode: "none" | "pan" | "node"; node?: AtlasNode; sx: number; sy: number }>({ mode: "none", sx: 0, sy: 0 });
  const hoveredRef = useRef<AtlasNode | null>(null);
  const cooldownRef = useRef(400);
  const animRef = useRef(0);

  const [loading, setLoading] = useState(true);
  const [regions, setRegions] = useState<{ field: string; concepts: number }[]>([]);
  const [selected, setSelected] = useState<AtlasNode | null>(null);
  const [explanation, setExplanation] = useState<string>("");
  const [neighbors, setNeighbors] = useState<{ id: string; name: string; relationship?: string }[]>([]);

  const { locale } = useLocaleStore();
  const he = locale === "he";
  const { trail, addStop, jumpTo } = useAtlasStore();

  // World size (virtual coordinates)
  const WORLD = 2400;

  // ── Load the universe ──
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams({ limit: "250" });
        if (userId) params.set("user_id", userId);
        const res = await fetch(`${API_BASE}/atlas?${params}`);
        if (!res.ok) throw new Error(`atlas ${res.status}`);
        const data = await res.json();

        // Field centroids arranged on a ring — regions of gravity
        const fields: string[] = (data.regions || []).map((r: any) => r.field);
        const centroids = new Map<string, { x: number; y: number }>();
        const R = WORLD * 0.3;
        fields.forEach((f, i) => {
          const angle = (i / Math.max(fields.length, 1)) * Math.PI * 2;
          centroids.set(f, { x: WORLD / 2 + R * Math.cos(angle), y: WORLD / 2 + R * Math.sin(angle) });
        });
        centroidsRef.current = centroids;

        // Nodes start near the mean of their fields' centroids —
        // border concepts land on the seams automatically
        nodesRef.current = (data.nodes || []).map((n: any) => {
          const span: string[] = n.field_span || [];
          let cx = WORLD / 2, cy = WORLD / 2, k = 0;
          for (const f of span) {
            const c = centroids.get(f);
            if (c) { cx += c.x; cy += c.y; k++; }
          }
          if (k > 0) { cx = (cx - WORLD / 2) / k; cy = (cy - WORLD / 2) / k; }
          return {
            ...n,
            x: cx + (Math.random() - 0.5) * 260,
            y: cy + (Math.random() - 0.5) * 260,
            vx: 0, vy: 0,
          };
        });
        edgesRef.current = data.edges || [];
        if (!cancelled) {
          setRegions(data.regions || []);
          setLoading(false);
          cooldownRef.current = 400;
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  // ── Resize ──
  useEffect(() => {
    const resize = () => {
      const c = canvasRef.current, el = containerRef.current;
      if (c && el) { c.width = el.clientWidth; c.height = el.clientHeight; }
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // ── Physics + render loop ──
  useEffect(() => {
    if (loading) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let running = true;

    const nodeMap = new Map(nodesRef.current.map((n) => [n.id, n]));

    const step = () => {
      if (!running) return;
      const nodes = nodesRef.current;
      const cam = cameraRef.current;

      // Physics with cooldown — stops burning CPU when settled
      if (cooldownRef.current > 0) {
        cooldownRef.current--;
        const alpha = Math.max(0.02, cooldownRef.current / 400) * 0.6;

        for (const n of nodes) {
          // Gravity toward the mean of this node's field centroids
          const span = n.field_span || [];
          let gx = WORLD / 2, gy = WORLD / 2, k = 0;
          for (const f of span) {
            const c = centroidsRef.current.get(f);
            if (c) { gx += c.x; gy += c.y; k++; }
          }
          if (k > 0) { gx = (gx - WORLD / 2) / k; gy = (gy - WORLD / 2) / k; }
          n.vx += (gx - n.x) * 0.002 * alpha;
          n.vy += (gy - n.y) * 0.002 * alpha;
        }

        // Repulsion (grid-bucketed would be faster; 250 nodes is fine O(n²))
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            const dx = b.x - a.x, dy = b.y - a.y;
            const d2 = dx * dx + dy * dy || 1;
            if (d2 < 90000) {
              const f = (2200 / d2) * alpha;
              const d = Math.sqrt(d2);
              a.vx -= (dx / d) * f; a.vy -= (dy / d) * f;
              b.vx += (dx / d) * f; b.vy += (dy / d) * f;
            }
          }
        }

        // Edge springs
        for (const e of edgesRef.current) {
          const a = nodeMap.get(e.source_id), b = nodeMap.get(e.target_id);
          if (!a || !b) continue;
          const dx = b.x - a.x, dy = b.y - a.y;
          const d = Math.sqrt(dx * dx + dy * dy) || 1;
          const f = (d - 140) * 0.002 * alpha;
          a.vx += (dx / d) * f; a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
        }

        for (const n of nodes) {
          if (dragRef.current.node === n) continue;
          n.vx *= 0.85; n.vy *= 0.85;
          n.x += n.vx; n.y += n.vy;
        }
      }

      // ── Render ──
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(cam.x, cam.y);
      ctx.scale(cam.scale, cam.scale);

      // Region glows
      for (const [field, c] of centroidsRef.current) {
        const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, 420);
        grad.addColorStop(0, fieldColor(field, 0.10));
        grad.addColorStop(1, "transparent");
        ctx.fillStyle = grad;
        ctx.fillRect(c.x - 420, c.y - 420, 840, 840);
        ctx.font = `600 ${22}px system-ui`;
        ctx.fillStyle = fieldColor(field, 0.5);
        ctx.textAlign = "center";
        ctx.fillText(field, c.x, c.y - 380);
      }

      // Edges
      ctx.lineWidth = 0.6 / cam.scale;
      for (const e of edgesRef.current) {
        const a = nodeMap.get(e.source_id), b = nodeMap.get(e.target_id);
        if (!a || !b) continue;
        const hot = hoveredRef.current && (e.source_id === hoveredRef.current.id || e.target_id === hoveredRef.current.id);
        ctx.strokeStyle = hot ? "rgba(232,185,49,0.55)" : "rgba(255,255,255,0.05)";
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }

      // Journey trail — the Ariadne thread
      const trailNodes = trail.map((s) => nodeMap.get(s.id)).filter(Boolean) as AtlasNode[];
      if (trailNodes.length > 1) {
        ctx.lineWidth = 2 / cam.scale;
        for (let i = 1; i < trailNodes.length; i++) {
          const opacity = 0.15 + (i / trailNodes.length) * 0.5;
          ctx.strokeStyle = `rgba(232,185,49,${opacity})`;
          ctx.beginPath();
          ctx.moveTo(trailNodes[i - 1].x, trailNodes[i - 1].y);
          ctx.lineTo(trailNodes[i].x, trailNodes[i].y);
          ctx.stroke();
        }
      }

      // Nodes
      for (const n of nodesRef.current) {
        const r = Math.max(3.5, Math.min(13, 3 + n.paper_count * 0.25));
        const color = CONSENSUS_COLORS[n.consensus_status || "emerging"] || "#58A6FF";
        // Fog: unexplored = dim, in_progress = half, explored = full
        const fogAlpha = !userId || !n.fog ? 0.85
          : n.fog === "explored" ? 1 : n.fog === "in_progress" ? 0.6 : 0.28;

        const isSel = selected?.id === n.id;
        const isHov = hoveredRef.current?.id === n.id;

        ctx.globalAlpha = isSel || isHov ? 1 : fogAlpha;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Border concept: seam ring in second field's color
        if (n.is_border && (n.field_span?.length || 0) >= 2) {
          ctx.lineWidth = 2 / cam.scale;
          ctx.strokeStyle = fieldColor(n.field_span![1], 0.9);
          ctx.stroke();
        }
        if (isSel || isHov) {
          ctx.lineWidth = 2.5 / cam.scale;
          ctx.strokeStyle = "#fff";
          ctx.stroke();
        }

        // Labels when zoomed in / hovered / on the trail
        if (cam.scale > 0.7 || isHov || isSel || trail.some((s) => s.id === n.id)) {
          ctx.font = `${isHov || isSel ? "600 " : ""}${12 / cam.scale}px system-ui`;
          ctx.fillStyle = isHov || isSel ? "#fff" : "rgba(255,255,255,0.55)";
          ctx.textAlign = "center";
          const label = n.name.length > 28 ? n.name.slice(0, 25) + "…" : n.name;
          ctx.fillText(label, n.x, n.y - r - 5 / cam.scale);
        }
        ctx.globalAlpha = 1;
      }
      ctx.restore();

      // ── Minimap ──
      const mm = minimapRef.current;
      const mctx = mm?.getContext("2d");
      if (mm && mctx) {
        const s = mm.width / WORLD;
        mctx.clearRect(0, 0, mm.width, mm.height);
        mctx.fillStyle = "rgba(13,17,23,0.9)";
        mctx.fillRect(0, 0, mm.width, mm.height);
        for (const n of nodesRef.current) {
          mctx.fillStyle = CONSENSUS_COLORS[n.consensus_status || "emerging"] || "#58A6FF";
          mctx.globalAlpha = 0.7;
          mctx.fillRect(n.x * s - 1, n.y * s - 1, 2, 2);
        }
        mctx.globalAlpha = 1;
        // Viewport rectangle — "you are here"
        const vx = (-cam.x / cam.scale) * s;
        const vy = (-cam.y / cam.scale) * s;
        const vw = (W / cam.scale) * s;
        const vh = (H / cam.scale) * s;
        mctx.strokeStyle = "#E8B931";
        mctx.lineWidth = 1.5;
        mctx.strokeRect(vx, vy, vw, vh);
      }

      animRef.current = requestAnimationFrame(step);
    };

    animRef.current = requestAnimationFrame(step);
    return () => { running = false; cancelAnimationFrame(animRef.current); };
  }, [loading, selected, trail, userId]);

  // ── Coordinate transforms ──
  const toWorld = useCallback((mx: number, my: number) => {
    const cam = cameraRef.current;
    return { x: (mx - cam.x) / cam.scale, y: (my - cam.y) / cam.scale };
  }, []);

  const nodeAt = useCallback((mx: number, my: number): AtlasNode | null => {
    const { x, y } = toWorld(mx, my);
    for (const n of nodesRef.current) {
      const r = Math.max(5, Math.min(14, 3 + n.paper_count * 0.25)) + 4;
      if ((n.x - x) ** 2 + (n.y - y) ** 2 < r * r) return n;
    }
    return null;
  }, [toWorld]);

  // ── Interactions ──
  const onMouseDown = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const n = nodeAt(mx, my);
    dragRef.current = n
      ? { mode: "node", node: n, sx: mx, sy: my }
      : { mode: "pan", sx: mx, sy: my };
  };

  const onMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const d = dragRef.current;
    const cam = cameraRef.current;

    if (d.mode === "pan") {
      cam.x += mx - d.sx; cam.y += my - d.sy;
      d.sx = mx; d.sy = my;
    } else if (d.mode === "node" && d.node) {
      const w = toWorld(mx, my);
      d.node.x = w.x; d.node.y = w.y;
      cooldownRef.current = Math.max(cooldownRef.current, 60);
    } else {
      hoveredRef.current = nodeAt(mx, my);
      canvasRef.current!.style.cursor = hoveredRef.current ? "pointer" : "grab";
    }
  };

  const onMouseUp = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const d = dragRef.current;
    const moved = Math.abs(mx - d.sx) + Math.abs(my - d.sy) > 6;
    if (d.mode === "node" && d.node && !moved) selectNode(d.node);
    dragRef.current = { mode: "none", sx: 0, sy: 0 };
  };

  const onWheel = (e: React.WheelEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const cam = cameraRef.current;
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    const next = Math.max(0.15, Math.min(4, cam.scale * factor));
    // zoom toward cursor
    cam.x = mx - ((mx - cam.x) / cam.scale) * next;
    cam.y = my - ((my - cam.y) / cam.scale) * next;
    cam.scale = next;
  };

  const centerOn = useCallback((n: AtlasNode) => {
    const canvas = canvasRef.current!;
    const cam = cameraRef.current;
    cam.scale = Math.max(cam.scale, 1.1);
    cam.x = canvas.width / 2 - n.x * cam.scale;
    cam.y = canvas.height / 2 - n.y * cam.scale;
  }, []);

  const selectNode = useCallback(async (n: AtlasNode) => {
    setSelected(n);
    centerOn(n);
    addStop({ id: n.id, name: n.name, kind: "concept", field: (n.field_span || [])[0] });

    // Load explanation + neighbors for the side panel
    setExplanation("");
    setNeighbors([]);
    try {
      const [expRes, nbRes] = await Promise.allSettled([
        fetch(`${API_BASE}/features/explain/${n.id}?locale=${locale}`),
        fetch(`${API_BASE}/graph/concepts/${n.id}/neighbors?depth=1`),
      ]);
      if (expRes.status === "fulfilled" && expRes.value.ok) {
        const d = await expRes.value.json();
        setExplanation(d.simple_explanation || d.definition || "");
      }
      if (nbRes.status === "fulfilled" && nbRes.value.ok) {
        const d = await nbRes.value.json();
        setNeighbors((d.related || []).map((r: any) => ({
          id: r.concept?.id, name: r.concept?.name, relationship: r.relationship_type,
        })).filter((x: any) => x.id));
      }
    } catch { /* panel stays minimal */ }
  }, [addStop, centerOn, locale]);

  const travelTo = useCallback((id: string) => {
    const n = nodesRef.current.find((x) => x.id === id);
    if (n) selectNode(n);
  }, [selectNode]);

  const minimapJump = (e: React.MouseEvent) => {
    const mm = minimapRef.current!;
    const rect = mm.getBoundingClientRect();
    const s = mm.width / WORLD;
    const wx = (e.clientX - rect.left) / s;
    const wy = (e.clientY - rect.top) / s;
    const canvas = canvasRef.current!;
    const cam = cameraRef.current;
    cam.x = canvas.width / 2 - wx * cam.scale;
    cam.y = canvas.height / 2 - wy * cam.scale;
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-text-tertiary">
        <Compass size={32} className="text-accent-gold animate-pulse" />
        <p className="text-sm">{he ? "טוען את יקום הידע..." : "Loading the knowledge universe..."}</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-[#0a0e14]">
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onWheel={onWheel}
      />

      {/* Breadcrumb — where am I */}
      <div className="absolute top-3 left-3 right-3 flex items-center gap-1.5 pointer-events-none">
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface/85 border border-border backdrop-blur pointer-events-auto max-w-full overflow-x-auto">
          <MapPin size={12} className="text-accent-gold shrink-0" />
          {trail.length === 0 ? (
            <span className="text-xs text-text-tertiary whitespace-nowrap">
              {he ? "לחץ על כוכב כדי לצאת למסע" : "Click a star to begin your journey"}
            </span>
          ) : (
            trail.slice(-5).map((s, i, arr) => (
              <span key={s.id} className="flex items-center gap-1.5 whitespace-nowrap">
                <button
                  onClick={() => { jumpTo(s.id); travelTo(s.id); }}
                  className={`text-xs hover:text-accent-gold transition-colors ${
                    i === arr.length - 1 ? "text-accent-gold font-medium" : "text-text-secondary"
                  }`}
                >
                  {s.name}
                </button>
                {i < arr.length - 1 && <span className="text-text-tertiary text-xs">›</span>}
              </span>
            ))
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 px-3 py-2 rounded-lg bg-surface/85 border border-border backdrop-blur text-[10px] space-y-1">
        {Object.entries({
          consensus: he ? "מוסכם" : "Consensus",
          contested: he ? "במחלוקת" : "Contested",
          emerging: he ? "מתגבש" : "Emerging",
          unverified: he ? "לא מאומת" : "Unverified",
        }).map(([k, label]) => (
          <div key={k} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: CONSENSUS_COLORS[k] }} />
            <span className="text-text-secondary">{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 pt-1 border-t border-border">
          <span className="w-2 h-2 rounded-full border-2" style={{ borderColor: "#BC8CFF", background: "#E8B931" }} />
          <span className="text-text-secondary">{he ? "מושג-גבול (בין-תחומי)" : "Border concept"}</span>
        </div>
      </div>

      {/* Minimap */}
      <canvas
        ref={minimapRef}
        width={168}
        height={126}
        onClick={minimapJump}
        className="absolute bottom-3 right-3 rounded-lg border border-border cursor-crosshair"
      />

      {/* Side panel — dive INTO without leaving the map */}
      {selected && (
        <div className="absolute top-14 right-3 w-[320px] max-h-[calc(100%-8rem)] overflow-y-auto rounded-xl bg-surface/95 border border-border backdrop-blur shadow-xl">
          <div className="flex items-start justify-between p-4 pb-2">
            <div>
              <h3 className="text-sm font-bold text-foreground">{selected.name}</h3>
              <div className="flex flex-wrap items-center gap-1.5 mt-1">
                {(selected.field_span || []).map((fld) => (
                  <span key={fld} className="text-[10px] px-1.5 py-0.5 rounded-full"
                        style={{ background: fieldColor(fld, 0.15), color: fieldColor(fld, 1) }}>
                    {fld}
                  </span>
                ))}
                <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                      style={{ background: `${CONSENSUS_COLORS[selected.consensus_status || "emerging"]}22`,
                               color: CONSENSUS_COLORS[selected.consensus_status || "emerging"] }}>
                  {selected.consensus_status || "emerging"}
                </span>
              </div>
            </div>
            <button onClick={() => setSelected(null)} className="text-text-tertiary hover:text-foreground p-1">
              <X size={14} />
            </button>
          </div>

          <div className="px-4 pb-4 space-y-3">
            {explanation ? (
              <p className="text-xs text-text-secondary leading-relaxed">{explanation}</p>
            ) : (
              <p className="text-xs text-text-tertiary animate-pulse">{he ? "טוען הסבר..." : "Loading..."}</p>
            )}

            {neighbors.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1.5 flex items-center gap-1">
                  <Route size={10} /> {he ? "המשך המסע" : "Continue the journey"}
                </p>
                <div className="space-y-1">
                  {neighbors.slice(0, 6).map((nb) => (
                    <button
                      key={nb.id}
                      onClick={() => travelTo(nb.id)}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg bg-surface-sunken hover:bg-surface-hover
                                 text-xs text-foreground transition-colors flex items-center justify-between gap-2"
                    >
                      <span className="truncate">{nb.name}</span>
                      <span className="text-[9px] text-text-tertiary shrink-0">
                        {(nb.relationship || "").replace(/_/g, " ").toLowerCase()}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-2 pt-1">
              {onOpenConcept && (
                <button
                  onClick={() => onOpenConcept((selected.field_span || [])[0] || "", selected.id)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg
                             bg-accent-gold text-background text-xs font-medium hover:bg-accent-gold/90"
                >
                  <BookOpen size={12} /> {he ? "פתח שיעור מלא" : "Open full lesson"}
                </button>
              )}
              {onSend && (
                <button
                  onClick={() => onSend(he
                    ? `ספר לי על ${selected.name} ואיך הוא מתחבר לתחומים אחרים`
                    : `Tell me about ${selected.name} and how it bridges to other fields`)}
                  className="px-3 py-2 rounded-lg bg-surface-sunken text-xs text-text-secondary hover:text-foreground"
                >
                  {he ? "שאל" : "Ask"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Region summary strip */}
      <div className="absolute top-14 left-3 flex flex-col gap-1 max-h-[40%] overflow-y-auto pointer-events-none">
        {regions.slice(0, 8).map((r) => (
          <div key={r.field} className="px-2 py-1 rounded bg-surface/70 backdrop-blur text-[10px] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: fieldColor(r.field) }} />
            <span className="text-text-secondary">{r.field}</span>
            <span className="text-text-tertiary">{r.concepts}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
