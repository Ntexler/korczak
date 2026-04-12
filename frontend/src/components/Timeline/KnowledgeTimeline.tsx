"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, Play, Pause, SkipBack, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getFieldTimeline, getTimelineFields, getConceptTypeTimeline } from "@/lib/api";

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

interface FieldInfo {
  type: string;
  count: number;
}

interface TopConcept {
  id: string;
  name: string;
  confidence: number;
  paper_count: number;
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

const FIELD_COLORS = [
  "#E8B931", "#58A6FF", "#3FB950", "#D29922", "#BC8CFF",
  "#F78166", "#F85149", "#8B949E", "#E6EDF3", "#A371F7",
];

export default function KnowledgeTimeline({ onClose }: TimelineProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [fields, setFields] = useState<FieldInfo[]>([]);
  const [activeField, setActiveField] = useState<string | null>(null);
  const [topConcepts, setTopConcepts] = useState<TopConcept[]>([]);
  const [topPapers, setTopPapers] = useState<Record<string, any[]>>({});
  const [hoveredYear, setHoveredYear] = useState<{ year: number; count: number; x: number; y: number } | null>(null);
  const dataRef = useRef<{ papers: YearData[]; milestones: Milestone[] }>({ papers: [], milestones: [] });
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const { locale } = useLocaleStore();

  // Load available fields on mount
  useEffect(() => {
    getTimelineFields()
      .then((res) => setFields(res.fields || []))
      .catch(() => {});
  }, []);

  const buildTimeline = useCallback(async () => {
    if (!svgRef.current) return;
    setLoading(true);
    setTopConcepts([]);
    setTopPapers({});

    try {
      let data;
      if (activeField) {
        const res = await getConceptTypeTimeline(activeField, 1950, 2026);
        data = {
          papers_by_year: res.papers_by_year || [],
          milestones: [],
        };
        setTopConcepts(res.top_concepts || []);
        setTopPapers(res.top_papers_by_year || {});
      } else {
        data = await getFieldTimeline(1950, 2026);
      }

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

      // Clip path for zoom
      const defs = svg.append("defs");
      defs.append("clipPath").attr("id", "chart-clip")
        .append("rect").attr("width", innerWidth).attr("height", innerHeight);

      const gradient = defs.append("linearGradient")
        .attr("id", "timelineGradient")
        .attr("x1", "0%").attr("y1", "0%")
        .attr("x2", "0%").attr("y2", "100%");
      const fieldColor = activeField
        ? FIELD_COLORS[fields.findIndex((f) => f.type === activeField) % FIELD_COLORS.length]
        : "#E8B931";
      gradient.append("stop").attr("offset", "0%").attr("stop-color", fieldColor).attr("stop-opacity", 0.3);
      gradient.append("stop").attr("offset", "100%").attr("stop-color", fieldColor).attr("stop-opacity", 0.02);

      const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

      // Scales
      const yearExtent = d3.extent(papers, (d) => d.year) as [number, number];
      const x = d3.scaleLinear().domain(yearExtent).range([0, innerWidth]);
      const maxCount = d3.max(papers, (d) => d.count) || 1;
      const y = d3.scaleLinear().domain([0, maxCount * 1.2]).range([innerHeight, 0]);

      // Axes
      const xAxis = g.append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x).tickFormat(d3.format("d")).ticks(10));
      xAxis.selectAll("text").attr("fill", "#8B949E").attr("font-size", "11px");
      xAxis.selectAll(".domain, .tick line").attr("stroke", "#2D3548");

      const yAxis = g.append("g")
        .attr("class", "y-axis")
        .call(d3.axisLeft(y).ticks(5));
      yAxis.selectAll("text").attr("fill", "#8B949E").attr("font-size", "11px");
      yAxis.selectAll(".domain, .tick line").attr("stroke", "#2D3548");

      // Chart content group (clipped for zoom)
      const chartContent = g.append("g").attr("clip-path", "url(#chart-clip)");

      // Area
      const area = d3.area<YearData>()
        .x((d) => x(d.year))
        .y0(innerHeight)
        .y1((d) => y(d.count))
        .curve(d3.curveMonotoneX);

      chartContent.append("path")
        .datum(papers)
        .attr("fill", "url(#timelineGradient)")
        .attr("d", area);

      // Line
      const line = d3.line<YearData>()
        .x((d) => x(d.year))
        .y((d) => y(d.count))
        .curve(d3.curveMonotoneX);

      chartContent.append("path")
        .datum(papers)
        .attr("fill", "none")
        .attr("stroke", fieldColor)
        .attr("stroke-width", 2.5)
        .attr("d", line);

      // Data point dots
      chartContent.selectAll(".dot")
        .data(papers)
        .enter()
        .append("circle")
        .attr("class", "dot")
        .attr("cx", (d) => x(d.year))
        .attr("cy", (d) => y(d.count))
        .attr("r", 4)
        .attr("fill", fieldColor)
        .attr("stroke", "#0C0F14")
        .attr("stroke-width", 1.5)
        .attr("cursor", "pointer")
        .attr("opacity", 0.8)
        .on("mouseenter", function (event, d) {
          d3.select(this).attr("r", 7).attr("opacity", 1);
          const rect = svgRef.current!.getBoundingClientRect();
          setHoveredYear({
            year: d.year,
            count: d.count,
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
          });
        })
        .on("mouseleave", function () {
          d3.select(this).attr("r", 4).attr("opacity", 0.8);
          setHoveredYear(null);
        });

      // Milestones
      milestones.forEach((m) => {
        const mx = x(m.year);
        if (mx < 0 || mx > innerWidth) return;

        chartContent.append("line")
          .attr("x1", mx).attr("y1", 0)
          .attr("x2", mx).attr("y2", innerHeight)
          .attr("stroke", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("stroke-width", 1)
          .attr("stroke-dasharray", "4,4")
          .attr("opacity", 0.6);

        const diamondSize = 6 + m.significance * 6;
        chartContent.append("path")
          .attr("d", d3.symbol().type(d3.symbolDiamond).size(diamondSize * diamondSize)())
          .attr("transform", `translate(${mx},${-10})`)
          .attr("fill", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("cursor", "pointer")
          .append("title")
          .text(`${m.year}: ${m.title}${m.description ? ` — ${m.description}` : ""}`);

        chartContent.append("text")
          .attr("x", mx)
          .attr("y", -20)
          .attr("text-anchor", "middle")
          .attr("fill", MILESTONE_COLORS[m.milestone_type] || "#8B949E")
          .attr("font-size", "10px")
          .text(m.title.length > 25 ? m.title.slice(0, 23) + "..." : m.title);
      });

      // Playhead
      chartContent.append("line")
        .attr("class", "playhead")
        .attr("x1", 0).attr("y1", 0)
        .attr("x2", 0).attr("y2", innerHeight)
        .attr("stroke", "#E8B931")
        .attr("stroke-width", 2)
        .attr("opacity", 0);

      // Zoom behavior
      const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([1, 8])
        .translateExtent([[0, 0], [width, height]])
        .on("zoom", (event) => {
          const newX = event.transform.rescaleX(x);
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (xAxis as any).call(d3.axisBottom(newX).tickFormat((d: any) => String(d)).ticks(10));
          xAxis.selectAll("text").attr("fill", "#8B949E").attr("font-size", "11px");
          xAxis.selectAll(".domain, .tick line").attr("stroke", "#2D3548");

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          chartContent.select("path[d^='M']").attr("d", area.x((d: any) => newX(d.year)) as any);
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          chartContent.selectAll<SVGPathElement, any>("path").filter(function () {
            return d3.select(this).attr("stroke") === fieldColor;
          }).attr("d", line.x((d: any) => newX(d.year)) as any);

          chartContent.selectAll<SVGCircleElement, YearData>(".dot")
            .attr("cx", (d) => newX(d.year));
        });

      svg.call(zoom);
      zoomRef.current = zoom;

      // Axis labels
      svg.append("text")
        .attr("x", width / 2)
        .attr("y", height - 10)
        .attr("text-anchor", "middle")
        .attr("fill", "#8B949E")
        .attr("font-size", "12px")
        .text(locale === "he" ? "שנה" : "Year");

      svg.append("text")
        .attr("x", -(height / 2))
        .attr("y", 15)
        .attr("transform", "rotate(-90)")
        .attr("text-anchor", "middle")
        .attr("fill", "#8B949E")
        .attr("font-size", "12px")
        .text(locale === "he" ? "מאמרים" : "Papers");

    } catch (err) {
      console.error("Timeline error:", err);
    } finally {
      setLoading(false);
    }
  }, [locale, activeField, fields]);

  useEffect(() => {
    buildTimeline();
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
    }, 200);

    return () => clearInterval(interval);
  }, [playing, currentYear]);

  const handleReset = () => {
    setPlaying(false);
    setCurrentYear(null);
  };

  const handleZoom = (factor: number) => {
    if (!svgRef.current || !zoomRef.current) return;
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, factor);
  };

  const handleResetZoom = () => {
    if (!svgRef.current || !zoomRef.current) return;
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity);
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-foreground">
            {locale === "he" ? "ציר הזמן של הידע" : "Timeline of Knowledge"}
          </h2>
          {activeField && (
            <span className="px-2.5 py-0.5 rounded-full bg-accent-gold/15 text-accent-gold text-sm font-medium">
              {activeField}
            </span>
          )}
          {currentYear && (
            <span className="px-2 py-0.5 rounded bg-surface-sunken text-foreground text-sm font-mono">
              {currentYear}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={handleReset} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary" title="Reset playback">
            <SkipBack size={16} />
          </button>
          <button onClick={() => setPlaying(!playing)} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary" title={playing ? "Pause" : "Play"}>
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <span className="mx-1 w-px h-4 bg-border" />
          <button onClick={() => handleZoom(1.5)} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary" title="Zoom in">
            <ZoomIn size={16} />
          </button>
          <button onClick={() => handleZoom(0.67)} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary" title="Zoom out">
            <ZoomOut size={16} />
          </button>
          <button onClick={handleResetZoom} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary" title="Reset zoom">
            <Maximize2 size={16} />
          </button>
          <span className="mx-1 w-px h-4 bg-border" />
          <button onClick={onClose} className="p-1.5 rounded hover:bg-surface-hover text-text-secondary">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Field selector tabs */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-border overflow-x-auto">
        <button
          onClick={() => setActiveField(null)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
            !activeField ? "bg-accent-gold/15 text-accent-gold" : "hover:bg-surface-hover text-text-secondary"
          }`}
        >
          {locale === "he" ? "הכל" : "All Fields"}
        </button>
        {fields.map((f, i) => (
          <button
            key={f.type}
            onClick={() => setActiveField(f.type)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              activeField === f.type ? "bg-accent-gold/15 text-accent-gold" : "hover:bg-surface-hover text-text-secondary"
            }`}
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: FIELD_COLORS[i % FIELD_COLORS.length] }} />
            {f.type} ({f.count})
          </button>
        ))}
      </div>

      {/* Main area: chart + optional detail sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chart */}
        <div className="flex-1 relative overflow-hidden">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="flex items-center gap-3 text-text-secondary">
                <div className="w-5 h-5 border-2 border-accent-gold border-t-transparent rounded-full animate-spin" />
                <span>{locale === "he" ? "בונה ציר זמן..." : "Building timeline..."}</span>
              </div>
            </div>
          )}
          {!loading && dataRef.current.papers.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="text-center max-w-md px-6">
                <p className="text-lg text-text-secondary mb-2">
                  {activeField
                    ? (locale === "he" ? `אין נתונים עבור "${activeField}"` : `No data for "${activeField}" yet`)
                    : (locale === "he" ? "אין עדיין נתוני ציר זמן" : "No timeline data yet")}
                </p>
                <p className="text-sm text-text-tertiary">
                  {locale === "he"
                    ? "ציר הזמן ייבנה אוטומטית ככל שגרף הידע יתפתח."
                    : "The timeline builds automatically as the knowledge graph evolves."}
                </p>
              </div>
            </div>
          )}

          {/* Hover tooltip */}
          {hoveredYear && (
            <div
              className="absolute z-20 pointer-events-none bg-surface border border-border rounded-lg px-3 py-2 shadow-lg"
              style={{ left: hoveredYear.x + 12, top: hoveredYear.y - 10 }}
            >
              <p className="text-sm font-bold text-foreground">{hoveredYear.year}</p>
              <p className="text-xs text-text-secondary">
                {hoveredYear.count} {locale === "he" ? "מאמרים" : "papers"}
              </p>
              {topPapers[String(hoveredYear.year)]?.map((p: any, i: number) => (
                <p key={i} className="text-[11px] text-text-tertiary mt-1 max-w-xs truncate">
                  &bull; {p.title}
                </p>
              ))}
            </div>
          )}

          <svg ref={svgRef} className="w-full h-full" />
        </div>

        {/* Detail sidebar for active field */}
        {activeField && topConcepts.length > 0 && (
          <div className="w-72 border-l border-border bg-surface/50 overflow-y-auto flex-shrink-0">
            <div className="px-4 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">
                {locale === "he" ? "מושגים מובילים" : "Top Concepts"}
              </h3>
              <p className="text-xs text-text-tertiary mt-0.5">
                {locale === "he" ? `ב-${activeField}` : `in ${activeField}`}
              </p>
            </div>
            <div className="p-2 space-y-0.5">
              {topConcepts.map((c) => (
                <div key={c.id} className="px-3 py-2.5 rounded-lg hover:bg-surface-hover transition-colors">
                  <p className="text-sm text-foreground">{c.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                      <div className="h-full bg-accent-gold rounded-full" style={{ width: `${Math.round(c.confidence * 100)}%` }} />
                    </div>
                    <span className="text-[10px] text-text-tertiary font-mono">{Math.round(c.confidence * 100)}%</span>
                    {c.paper_count > 0 && (
                      <span className="text-[10px] text-text-tertiary">{c.paper_count}p</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Milestone legend (only when viewing all fields) */}
      {!activeField && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 border-t border-border text-[10px] text-text-secondary">
          {Object.entries(MILESTONE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
              <span>{type.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
