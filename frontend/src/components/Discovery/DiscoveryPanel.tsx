"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Search, AlertTriangle, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { getRisingStars, getResearchGaps } from "@/lib/api";
import { useLocaleStore } from "@/stores/localeStore";
import { useChatStore } from "@/stores/chatStore";

interface TrendingConcept {
  concept_id: string;
  name: string;
  type: string;
  recent_papers: number;
  trend_score: number;
}

interface RisingPaper {
  paper_id: string;
  title: string;
  citation_count: number;
  citation_velocity: number;
}

interface GapsSummary {
  total_gaps: number;
  orphan_concepts: number;
  missing_connections: number;
  low_evidence_controversies: number;
}

export default function DiscoveryPanel() {
  const { t } = useLocaleStore();
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const [trending, setTrending] = useState<TrendingConcept[]>([]);
  const [papers, setPapers] = useState<RisingPaper[]>([]);
  const [gaps, setGaps] = useState<GapsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedSection, setExpandedSection] = useState<string | null>("trending");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [risingData, gapsData] = await Promise.all([
          getRisingStars(90, 8).catch(() => ({ trending_concepts: [], rising_papers: [] })),
          getResearchGaps(undefined, 10).catch(() => ({ summary: null })),
        ]);
        setTrending(risingData.trending_concepts || []);
        setPapers(risingData.rising_papers || []);
        setGaps(gapsData.summary || null);
      } catch {
        // Silent fail — panel just shows empty state
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-surface-sunken rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Trending Concepts */}
      <section className="bg-surface/60 rounded-xl border border-border overflow-hidden">
        <button
          onClick={() => toggleSection("trending")}
          className="flex items-center justify-between w-full px-3 py-2.5 hover:bg-surface-hover transition-colors"
        >
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-accent-gold" />
            <span className="text-xs font-semibold text-foreground">{t.trendingConcepts}</span>
            {trending.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent-gold-dim text-accent-gold">
                {trending.length}
              </span>
            )}
          </div>
          {expandedSection === "trending" ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </button>

        {expandedSection === "trending" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="border-t border-border"
          >
            {trending.length === 0 ? (
              <p className="px-3 py-3 text-[11px] text-text-tertiary">{t.noData}</p>
            ) : (
              <div className="px-2 py-2 space-y-0.5">
                {trending.map((c) => (
                  <button
                    key={c.concept_id}
                    onClick={() => setSelectedConceptId(c.concept_id)}
                    className="flex items-center justify-between w-full px-2 py-1.5 rounded-lg
                      text-left hover:bg-surface-hover transition-colors group"
                  >
                    <div className="min-w-0">
                      <span className="text-xs text-text-secondary group-hover:text-foreground truncate block">
                        {c.name}
                      </span>
                      <span className="text-[10px] text-text-tertiary">
                        {c.recent_papers} {t.recentPapers}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-accent-gold ml-2 flex-shrink-0">
                      {c.trend_score}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </section>

      {/* Rising Papers */}
      <section className="bg-surface/60 rounded-xl border border-border overflow-hidden">
        <button
          onClick={() => toggleSection("papers")}
          className="flex items-center justify-between w-full px-3 py-2.5 hover:bg-surface-hover transition-colors"
        >
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-accent-blue" />
            <span className="text-xs font-semibold text-foreground">{t.risingPapers}</span>
            {papers.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-accent-blue">
                {papers.length}
              </span>
            )}
          </div>
          {expandedSection === "papers" ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </button>

        {expandedSection === "papers" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="border-t border-border"
          >
            {papers.length === 0 ? (
              <p className="px-3 py-3 text-[11px] text-text-tertiary">{t.noData}</p>
            ) : (
              <div className="px-2 py-2 space-y-0.5">
                {papers.map((p) => (
                  <div
                    key={p.paper_id}
                    className="px-2 py-1.5 rounded-lg hover:bg-surface-hover transition-colors"
                  >
                    <p className="text-xs text-text-secondary line-clamp-2">{p.title}</p>
                    <p className="text-[10px] text-text-tertiary mt-0.5">
                      {p.citation_count} {t.citations} &middot; {p.citation_velocity.toFixed(3)}/day
                    </p>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </section>

      {/* Research Gaps */}
      <section className="bg-surface/60 rounded-xl border border-border overflow-hidden">
        <button
          onClick={() => toggleSection("gaps")}
          className="flex items-center justify-between w-full px-3 py-2.5 hover:bg-surface-hover transition-colors"
        >
          <div className="flex items-center gap-2">
            <Search size={14} className="text-amber-400" />
            <span className="text-xs font-semibold text-foreground">{t.researchGaps}</span>
            {gaps && gaps.total_gaps > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400">
                {gaps.total_gaps}
              </span>
            )}
          </div>
          {expandedSection === "gaps" ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </button>

        {expandedSection === "gaps" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="border-t border-border"
          >
            {!gaps ? (
              <p className="px-3 py-3 text-[11px] text-text-tertiary">{t.noData}</p>
            ) : (
              <div className="px-3 py-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-secondary">{t.orphanConcepts}</span>
                  <span className="text-[11px] font-mono text-amber-400">{gaps.orphan_concepts}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-secondary">{t.missingConnections}</span>
                  <span className="text-[11px] font-mono text-amber-400">{gaps.missing_connections}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-secondary">{t.controversies}</span>
                  <span className="text-[11px] font-mono text-amber-400">{gaps.low_evidence_controversies}</span>
                </div>
                <div className="pt-1 border-t border-border">
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle size={11} className="text-amber-400" />
                    <span className="text-[10px] text-text-tertiary">
                      {gaps.total_gaps} {t.gapsFound}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </section>
    </div>
  );
}
