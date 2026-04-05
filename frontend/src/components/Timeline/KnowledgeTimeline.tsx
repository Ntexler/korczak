"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, Play, Pause, SkipBack } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface TimelineProps {
  onClose: () => void;
}

interface YearData {
  year: number;
  count: number;
}

interface Milestone {
  id: string;
  title: string;
  description?: string;
  milestone_type: string;
  year: number;
  significance: number;
}

const MILESTONE_COLORS: Record<string, string> = {
  paradigm_shift: "#F85149",
  breakthrough: "#3FB950",
  controversy: "#D29922",
  synthesis: "#58A6FF",
  split: "#BC8CFF",
  decline: "#8B949E",
  emergence: "#E8B931",
};

export default function KnowledgeTimeline({ onClose }: TimelineProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const animRef = useRef<number | null>(null);
  const dataRef = useRef<{ papers: YearData[]; milestones: Milestone[] }>({ papers: [], milestones: [] });
  const { locale } = useLocaleStore();

  const buildTimeline = useCallback(async () => {
    if (!svgRef.current) return;
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/timeline/field?year_start=1950&year_end=2026`);
      if (!res.ok) throw new Error("Failed to fetch timeline data");
      const data = await res.json();

      const papers: YearData[] = data.papers_by_year || [];
      const milestones: Milestone[] = data.milestones || [];
      dataRef.current = { papers, milestones };

      if (papers.length === 0) {
        setLoading(false);
        return;
      }

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();

      const width = svgRef.current.clientWidth;
      const height = svgRef.current.clientHeight;
      const margin = { top: 40, right: 40, bottom: 60, left: 60 };
      const innerWidth = width - margin.left - margin.right;
      const innerHeight = height - margin.top - margin.bottom;

      const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

      // Scales
      const yearExtent = d3.extent(papers, (d) => d.year) as [number, number];
      const x = d3.scaleLinear().domain(yearExtent).range([0, innerWidth]);
      const maxCount = d3.max(papers, (d) => d.count) || 1;
      const y = d3.scaleLinear().domain([0, maxCount * 1.2]).range([innerHeight, 0]);

      // X axis
      g.append("g")
        .attr("transform", `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x).tickFormat(d3.format("d")).ticks(10))
        .selectAll("text")
        .attr("fill", "#8B949E")
        .attr("font-size", "10px");

      g.selectAll(".domain, .tick line").attr("stroke", "#2D3548");

      // Y axis
      g.append("g")
        .call(d3.axisLeft(y).ticks(5))
        .selectAll("text")
        .attr("fill", "#8B949E")
        .attr("font-size", "10px");

      // Area chart for paper counts
      const area = d3.area<YearData>()
        .x((d) => x(d.year))
        .y0(innerHeight)
        .y1((d) => y(d.count))
        .curve(d3.curveMonotoneX);

      g.append("path")
        .datum(papers)
        .attr("fill", "url(#timelineGradient)")
        .attr("d", area);

      // Line on top
      const line = d3.line<YearData>()
        .x((d) => x(d.year))
        .y((d) => y(d.count))
        .curve(d3.curveMonotoneX);

      g.append("path")
        .datum(papers)
        .attr("fill", "none")
        .attr("stroke", "#E8B931")
        .attr("stroke-width", 2)
        .attr("d", line);

      // Gradient
      const defs = svg.append("defs");
      const gradient = defs.append("linearGradient")
        .attr("id", "timelineGradient")
        .attr("x1", "0%").attr("y1", "0%")
        .attr("x2", "0%").attr("y2", "100%");
      gradient.append("stop").attr("offset", "0%").attr("stop-color", "#E8B931").attr("stop-opacity", 0.3);
      gradient.append("stop").attr("offset", "100%").attr("stop-color", "#E8B931").attr("stop-opacity", 0.02);

      // Milestones as markers
      milestones.forEach((m) => {
        const mx = x(m.year);
        if (mx < 0 || mx > innerWidth) return;

        // Vertical line
        g.append("line")
          .attr("x1", mx).attr("y1", 0)
          .attr("x2", mx).attr("y2", innerHeight)
          .attr("stroke", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("stroke-width", 1)
          .attr("stroke-dasharray", "4,4")
          .attr("opacity", 0.6);

        // Diamond marker
        const diamondSize = 6 + m.significance * 6;
        g.append("path")
          .attr("d", d3.symbol().type(d3.symbolDiamond).size(diamondSize * diamondSize)())
          .attr("transform", `translate(${mx},${-10})`)
          .attr("fill", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("cursor", "pointer")
          .append("title")
          .text(`${m.year}: ${m.title}${m.description ? ` — ${m.description}` : ""}`);

        // Label
        g.append("text")
          .attr("x", mx)
          .attr("y", -20)
          .attr("text-anchor", "middle")
          .attr("fill", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("font-size", "9px")
          .text(m.title.length > 20 ? m.title.slice(0, 18) + "..." : m.title);
      });

      // Playhead line (for animation)
      g.append("line")
        .attr("class", "playhead")
        .attr("x1", 0).attr("y1", 0)
        .attr("x2", 0).attr("y2", innerHeight)
        .attr("stroke", "#E8B931")
        .attr("stroke-width", 2)
        .attr("opacity", 0);

      // Axis labels
      svg.append("text")
        .attr("x", width / 2)
        .attr("y", height - 10)
        .attr("text-anchor", "middle")
        .attr("fill", "#8B949E")
        .attr("font-size", "11px")
        .text(locale === "he" ? "שנה" : "Year");

      svg.append("text")
        .attr("x", -(height / 2))
        .attr("y", 15)
        .attr("transform", "rotate(-90)")
        .attr("text-anchor", "middle")
        .attr("fill", "#8B949E")
        .attr("font-size", "11px")
        .text(locale === "he" ? "מאמרים" : "Papers");

    } catch (err) {
      console.error("Timeline error:", err);
    } finally {
      setLoading(false);
    }
  }, [locale]);

  useEffect(() => {
    buildTimeline();
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [buildTimeline]);

  // Play animation
  useEffect(() => {
    if (!playing || !svgRef.current) return;

    const papers = dataRef.current.papers;
    if (papers.length === 0) return;

    const yearStart = papers[0].year;
    const yearEnd = papers[papers.length - 1].year;
    let year = currentYear || yearStart;

    const interval = setInterval(() => {
      year += 1;
      if (year > yearEnd) {
        setPlaying(false);
        return;
      }
      setCurrentYear(year);

      // Move playhead
      const svg = d3.select(svgRef.current);
      const width = svgRef.current!.clientWidth - 100;
      const progress = (year - yearStart) / (yearEnd - yearStart);
      svg.select(".playhead")
        .attr("x1", 60 + progress * width)
        .attr("x2", 60 + progress * width)
        .attr("opacity", 0.8);
    }, 200);

    return () => clearInterval(interval);
  }, [playing, currentYear]);

  const handleReset = () => {
    setPlaying(false);
    setCurrentYear(null);
    if (svgRef.current) {
      d3.select(svgRef.current).select(".playhead").attr("opacity", 0);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-foreground">
            {locale === "he" ? "ציר הזמן של הידע" : "Timeline of Knowledge"}
          </h2>
          {currentYear && (
            <span className="px-2 py-0.5 rounded bg-accent-gold/15 text-accent-gold text-sm font-mono">
              {currentYear}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="p-1.5 rounded hover:bg-surface-hover text-text-secondary"
            title="Reset"
          >
            <SkipBack size={16} />
          </button>
          <button
            onClick={() => setPlaying(!playing)}
            className="p-1.5 rounded hover:bg-surface-hover text-text-secondary"
            title={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Milestone legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 border-b border-border text-[10px] text-text-secondary">
        {Object.entries(MILESTONE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span>{type.replace(/_/g, " ")}</span>
          </div>
        ))}
      </div>

      {/* Timeline visualization */}
      <div className="flex-1 relative overflow-hidden">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex items-center gap-3 text-text-secondary">
              <div className="w-5 h-5 border-2 border-accent-gold border-t-transparent rounded-full animate-spin" />
              <span>{locale === "he" ? "בונה ציר זמן..." : "Building timeline..."}</span>
            </div>
          </div>
        )}
        <svg ref={svgRef} className="w-full h-full" />
      </div>
    </div>
  );
}
