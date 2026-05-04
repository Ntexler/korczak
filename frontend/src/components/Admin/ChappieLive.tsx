"use client";

import { useEffect, useState, useRef } from "react";
import {
  Bot, Search, BookOpen, AlertTriangle, CheckCircle, XCircle,
  Pause, Play, RotateCcw, Send, ArrowRight, Eye, Zap, Moon,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ─── Pixel Art Chappie (CSS-based) ──────────────────────────────────────────

type ChappieState = "idle" | "walking" | "thinking" | "reading" | "eureka" | "sleeping" | "returning";

function ChappieAvatar({ state, size = 64 }: { state: ChappieState; size?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId = 0;
    const px = size / 16; // pixel size

    const drawPixel = (x: number, y: number, color: string) => {
      ctx.fillStyle = color;
      ctx.fillRect(x * px, y * px, px, px);
    };

    const colors = {
      body: "#58A6FF",
      eye: "#E8B931",
      dark: "#1a1a2e",
      highlight: "#BC8CFF",
      book: "#3FB950",
      spark: "#E8B931",
    };

    const drawChappie = (frame: number) => {
      ctx.clearRect(0, 0, size, size);

      // Body (rounded robot shape)
      const bodyY = state === "walking" ? (frame % 2 === 0 ? 5 : 6) : 5;

      // Head
      for (let x = 5; x <= 10; x++) drawPixel(x, bodyY - 1, colors.body);
      for (let x = 4; x <= 11; x++) drawPixel(x, bodyY, colors.body);
      for (let x = 4; x <= 11; x++) drawPixel(x, bodyY + 1, colors.body);
      for (let x = 5; x <= 10; x++) drawPixel(x, bodyY + 2, colors.body);

      // Eyes
      if (state === "sleeping") {
        drawPixel(6, bodyY, colors.dark);
        drawPixel(7, bodyY, colors.dark);
        drawPixel(9, bodyY, colors.dark);
        drawPixel(10, bodyY, colors.dark);
      } else {
        drawPixel(6, bodyY, colors.eye);
        drawPixel(9, bodyY, colors.eye);
        // Blink
        if (frame % 30 === 0) {
          drawPixel(6, bodyY, colors.body);
          drawPixel(9, bodyY, colors.body);
        }
      }

      // Antenna
      drawPixel(7, bodyY - 2, colors.highlight);
      drawPixel(8, bodyY - 3, colors.highlight);
      if (state === "eureka" || state === "thinking") {
        // Antenna glow
        drawPixel(8, bodyY - 4, frame % 4 < 2 ? colors.spark : "transparent");
        drawPixel(9, bodyY - 4, frame % 4 >= 2 ? colors.spark : "transparent");
      }

      // Body
      for (let x = 5; x <= 10; x++) drawPixel(x, bodyY + 3, colors.body);
      for (let x = 6; x <= 9; x++) drawPixel(x, bodyY + 4, colors.body);

      // Legs
      if (state === "walking") {
        if (frame % 4 < 2) {
          drawPixel(6, bodyY + 5, colors.body);
          drawPixel(9, bodyY + 5, colors.body);
        } else {
          drawPixel(7, bodyY + 5, colors.body);
          drawPixel(8, bodyY + 5, colors.body);
        }
      } else {
        drawPixel(6, bodyY + 5, colors.body);
        drawPixel(9, bodyY + 5, colors.body);
      }

      // State-specific elements
      if (state === "reading" || state === "returning") {
        // Book in hand
        drawPixel(12, bodyY + 2, colors.book);
        drawPixel(13, bodyY + 2, colors.book);
        drawPixel(12, bodyY + 3, colors.book);
        drawPixel(13, bodyY + 3, colors.book);
      }

      if (state === "thinking") {
        // Thought dots
        const dotPhase = frame % 12;
        if (dotPhase < 4) drawPixel(13, bodyY - 1, colors.spark);
        if (dotPhase < 8) drawPixel(14, bodyY - 2, colors.spark);
        if (dotPhase < 12) drawPixel(15, bodyY - 3, colors.spark);
      }

      if (state === "eureka") {
        // Exclamation mark
        drawPixel(13, bodyY - 3, colors.spark);
        drawPixel(13, bodyY - 2, colors.spark);
        drawPixel(13, bodyY, colors.spark);
      }

      if (state === "sleeping") {
        // Z's
        const zPhase = Math.floor(frame / 8) % 3;
        ctx.fillStyle = colors.highlight;
        ctx.font = `${px * 2}px monospace`;
        ctx.fillText("z", (12 + zPhase) * px, (bodyY - zPhase) * px);
      }
    };

    const animate = () => {
      frameRef.current++;
      drawChappie(frameRef.current);
      animId = requestAnimationFrame(animate);
    };

    // Different frame rates for different states
    const intervalMs = state === "sleeping" ? 500 : state === "walking" ? 150 : 200;
    const interval = setInterval(() => {
      frameRef.current++;
    }, intervalMs);

    animId = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animId);
      clearInterval(interval);
    };
  }, [state, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="image-rendering-pixelated"
      style={{ imageRendering: "pixelated" }}
    />
  );
}


// ─── Live Feed ──────────────────────────────────────────────────────────────

interface FeedEntry {
  time: string;
  action: string;
  detail: string;
  type: "search" | "found" | "contradiction" | "author" | "accepted" | "rejected" | "started";
}

interface ChappieLiveProps {
  onClose?: () => void;
}

export default function ChappieLive({ onClose }: ChappieLiveProps) {
  const { locale, fonts: f } = useLocaleStore();
  const he = locale === "he";
  const [chappieState, setChappieState] = useState<ChappieState>("idle");
  const [currentSource, setCurrentSource] = useState("Waiting...");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [field, setField] = useState("Anthropology");
  const [peekOpen, setPeekOpen] = useState(false);
  const [peekConversation, setPeekConversation] = useState<{ q: string; a: string } | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });

  // Simulated live updates (in production, use WebSocket or SSE)
  const addFeedEntry = (entry: Omit<FeedEntry, "time">) => {
    const now = new Date().toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
    setFeed(prev => [{ ...entry, time: now }, ...prev].slice(0, 50));
  };

  // Start Chappie on a learning mission
  const startMission = async () => {
    setPaused(false);
    setChappieState("walking");
    setCurrentSource("Starting exploration...");
    addFeedEntry({ action: "started", detail: `Starting ${field} exploration`, type: "started" });

    // In production: call the learning agent API and stream updates
    // For now: simulate with API calls
    try {
      setChappieState("thinking");
      setCurrentSource("Analyzing knowledge gaps...");

      const weakRes = await fetch(`${API_BASE}/admin/consciousness/curiosities?field=${field}&limit=5`);
      const weakData = weakRes.ok ? await weakRes.json() : { curiosities: [] };

      const questions = weakData.curiosities || [];
      setProgress({ done: 0, total: Math.max(questions.length, 5) });

      for (let i = 0; i < Math.min(questions.length, 5); i++) {
        if (paused) break;

        const q = questions[i];
        setChappieState("walking");
        setCurrentSource("Semantic Scholar");
        setCurrentQuestion(q.question || `Exploring ${field} concept ${i + 1}`);
        addFeedEntry({
          action: `Searching for: ${(q.question || "").slice(0, 60)}...`,
          detail: `Source: Semantic Scholar`,
          type: "search",
        });

        // Actually search
        try {
          const searchRes = await fetch(
            `${API_BASE}/plugins/search/multi?query=${encodeURIComponent(q.concept_name || field)}&limit=3`
          );
          if (searchRes.ok) {
            const data = await searchRes.json();
            setChappieState("reading");
            addFeedEntry({
              action: `Found ${data.total} papers`,
              detail: `From: ${(data.sources_queried || []).join(", ")}`,
              type: "found",
            });

            if (data.papers?.[0]) {
              setPeekConversation({
                q: q.question || `What do we know about ${q.concept_name}?`,
                a: `Found: "${data.papers[0].title}" (${data.papers[0].publication_year || "?"}) — ${(data.papers[0].abstract || "").slice(0, 200)}...`,
              });
            }

            // Brief pause to show reading state
            await new Promise(r => setTimeout(r, 2000));
            setChappieState("eureka");
            await new Promise(r => setTimeout(r, 1000));
          }
        } catch { /* continue */ }

        setProgress(prev => ({ ...prev, done: i + 1 }));
      }

      setChappieState("returning");
      setCurrentSource("Done!");
      setCurrentQuestion("Mission complete");
      addFeedEntry({ action: "Mission complete", detail: `Explored ${field}`, type: "accepted" });

      await new Promise(r => setTimeout(r, 2000));
      setChappieState("idle");

    } catch (e) {
      setChappieState("idle");
      addFeedEntry({ action: "Error", detail: String(e), type: "rejected" });
    }
  };

  const sendCustomQuestion = () => {
    if (!customQuestion.trim()) return;
    addFeedEntry({
      action: `User asked: "${customQuestion}"`,
      detail: "Adding to exploration queue",
      type: "started",
    });
    setCurrentQuestion(customQuestion);
    setCustomQuestion("");
  };

  const FEED_ICONS: Record<string, any> = {
    search: Search,
    found: BookOpen,
    contradiction: AlertTriangle,
    author: Eye,
    accepted: CheckCircle,
    rejected: XCircle,
    started: Zap,
  };

  const FEED_COLORS: Record<string, string> = {
    search: "text-blue-400",
    found: "text-green-400",
    contradiction: "text-amber-400",
    author: "text-purple-400",
    accepted: "text-green-400",
    rejected: "text-red-400",
    started: "text-accent-gold",
  };

  const STATE_LABELS: Record<ChappieState, { en: string; he: string }> = {
    idle: { en: "Standing by", he: "ממתין" },
    walking: { en: "Exploring...", he: "מטייל..." },
    thinking: { en: "Thinking...", he: "חושב..." },
    reading: { en: "Reading...", he: "קורא..." },
    eureka: { en: "Found something!", he: "!מצא משהו" },
    sleeping: { en: "Sleeping", he: "ישן" },
    returning: { en: "Coming back!", he: "!חוזר" },
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border bg-surface shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bot size={20} className="text-accent-gold" />
            <div>
              <h2 className="text-base font-bold text-foreground" style={{ fontFamily: f.display }}>
                Chappie Live
              </h2>
              <p className="text-[10px] text-text-tertiary">
                {he ? STATE_LABELS[chappieState].he : STATE_LABELS[chappieState].en}
                {currentSource !== "Waiting..." && ` — ${currentSource}`}
              </p>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="text-text-tertiary hover:text-foreground text-lg">&times;</button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Chappie Animation Window */}
        <div className="flex flex-col items-center py-6 border-b border-border bg-[#0d1117]">
          <ChappieAvatar state={chappieState} size={96} />
          <p className="text-xs text-text-tertiary mt-2">
            {he ? STATE_LABELS[chappieState].he : STATE_LABELS[chappieState].en}
          </p>
          {progress.total > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <div className="w-32 h-1.5 rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent-gold transition-all duration-500"
                  style={{ width: `${(progress.done / progress.total) * 100}%` }}
                />
              </div>
              <span className="text-[10px] text-text-tertiary">{progress.done}/{progress.total}</span>
            </div>
          )}
        </div>

        {/* Current Question */}
        {currentQuestion && (
          <div className="px-5 py-3 border-b border-border bg-accent-gold/5">
            <p className="text-[10px] text-accent-gold uppercase tracking-wider mb-1">
              {he ? "שואל עכשיו" : "Currently asking"}
            </p>
            <p className="text-sm text-foreground">{currentQuestion}</p>
          </div>
        )}

        {/* Peek: Conversation */}
        {peekConversation && (
          <div className="px-5 py-3 border-b border-border">
            <button
              onClick={() => setPeekOpen(!peekOpen)}
              className="flex items-center gap-2 text-xs text-text-tertiary hover:text-text-secondary"
            >
              <Eye size={12} />
              {he ? "הצצה לשיחה" : "Peek at conversation"}
              <span className="text-[10px]">{peekOpen ? "▲" : "▼"}</span>
            </button>
            {peekOpen && (
              <div className="mt-2 space-y-2">
                <div className="px-3 py-2 rounded-lg bg-accent-gold/5 border border-accent-gold/20">
                  <p className="text-[10px] text-accent-gold mb-1">Chappie asks:</p>
                  <p className="text-xs text-foreground">{peekConversation.q}</p>
                </div>
                <div className="px-3 py-2 rounded-lg bg-surface border border-border">
                  <p className="text-[10px] text-text-tertiary mb-1">Source answers:</p>
                  <p className="text-xs text-text-secondary">{peekConversation.a}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Live Feed */}
        <div className="px-5 py-3">
          <h3 className="text-[10px] text-text-tertiary uppercase tracking-wider mb-3">
            {he ? "פעילות חיה" : "Live Feed"}
          </h3>
          <div className="space-y-2">
            {feed.length === 0 ? (
              <p className="text-xs text-text-tertiary text-center py-4">
                {he ? "צ'אפי ממתין להוראות" : "Chappie is waiting for a mission"}
              </p>
            ) : (
              feed.map((entry, i) => {
                const Icon = FEED_ICONS[entry.type] || Zap;
                const color = FEED_COLORS[entry.type] || "text-text-tertiary";
                return (
                  <div key={i} className="flex gap-2 text-xs">
                    <span className="text-text-tertiary w-10 shrink-0 text-right">{entry.time}</span>
                    <Icon size={12} className={`${color} shrink-0 mt-0.5`} />
                    <div>
                      <p className="text-foreground">{entry.action}</p>
                      <p className="text-text-tertiary">{entry.detail}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="px-5 py-3 border-t border-border bg-surface shrink-0 space-y-2">
        {/* Custom question */}
        <div className="flex gap-2">
          <input
            type="text"
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendCustomQuestion()}
            placeholder={he ? "תגיד לצ'אפי לבדוק..." : "Tell Chappie to check..."}
            className="flex-1 px-3 py-1.5 rounded-lg bg-surface-sunken border border-border
                       text-sm text-foreground placeholder:text-text-tertiary
                       focus:outline-none focus:border-accent-gold/50"
          />
          <button
            onClick={sendCustomQuestion}
            className="p-1.5 rounded-lg bg-accent-gold/10 text-accent-gold hover:bg-accent-gold/20"
          >
            <Send size={14} />
          </button>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={startMission}
            disabled={chappieState !== "idle" && chappieState !== "sleeping"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                       bg-accent-gold text-background hover:bg-accent-gold/90
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Play size={12} />
            {he ? "שלח ללמוד" : "Send to learn"}
          </button>
          <button
            onClick={() => { setPaused(true); setChappieState("sleeping"); }}
            disabled={chappieState === "idle" || chappieState === "sleeping"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                       bg-surface border border-border text-text-secondary
                       hover:text-foreground disabled:opacity-40 transition-colors"
          >
            <Pause size={12} />
            {he ? "עצור" : "Pause"}
          </button>
          <select
            value={field}
            onChange={(e) => setField(e.target.value)}
            className="px-2 py-1.5 rounded-lg bg-surface-sunken border border-border
                       text-xs text-foreground"
          >
            <option value="Anthropology">Anthropology</option>
            <option value="Medicine">Medicine</option>
            <option value="Psychology">Psychology</option>
            <option value="Philosophy">Philosophy</option>
            <option value="Economics">Economics</option>
            <option value="Sociology">Sociology</option>
            <option value="Computer Science">Computer Science</option>
          </select>
        </div>
      </div>
    </div>
  );
}
