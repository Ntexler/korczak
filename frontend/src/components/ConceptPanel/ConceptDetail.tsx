"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  X,
  BookOpen,
  GitBranch,
  Shield,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Compass,
  Download,
  Check,
} from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";
import { getConceptDetail, getConceptNeighbors, exportConceptToObsidian } from "@/lib/api";
import ConceptSummaries from "@/components/Social/ConceptSummaries";
import DiscussionThread from "@/components/Social/DiscussionThread";

interface KeyPaper {
  id: string;
  title: string;
  authors: { name: string }[];
  publication_year?: number;
  cited_by_count: number;
}

interface KeyClaim {
  claim_text: string;
  evidence_type: string;
  strength: string;
  confidence: number;
}

interface ConceptData {
  id: string;
  name: string;
  type: string;
  definition?: string;
  paper_count: number;
  trend: string;
  confidence: number;
  key_papers?: KeyPaper[];
  key_claims?: KeyClaim[];
}

interface NeighborData {
  concept: ConceptData;
  related: {
    concept: { id: string; name: string; type: string; definition?: string };
    relationship_type: string;
    confidence: number;
    explanation?: string;
  }[];
}

const REL_COLORS: Record<string, string> = {
  BUILDS_ON: "border-l-accent-green",
  CONTRADICTS: "border-l-accent-red",
  EXTENDS: "border-l-accent-blue",
  APPLIES: "border-l-accent-purple",
  RESPONDS_TO: "border-l-accent-amber",
  ANALOGOUS_TO: "border-l-pink-400",
  INTRODUCES: "border-l-accent-gold",
};

export default function ConceptDetail({ researcherId }: { researcherId?: string }) {
  const { selectedConceptId, conceptPanelOpen, setSelectedConceptId } =
    useChatStore();
  const { locale, t, fonts: f } = useLocaleStore();
  const [concept, setConcept] = useState<ConceptData | null>(null);
  const [neighbors, setNeighbors] = useState<NeighborData | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);

  useEffect(() => {
    if (!selectedConceptId) {
      setConcept(null);
      setNeighbors(null);
      return;
    }
    setLoading(true);
    Promise.all([
      getConceptDetail(selectedConceptId),
      getConceptNeighbors(selectedConceptId),
    ])
      .then(([c, n]) => {
        setConcept(c);
        setNeighbors(n);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedConceptId]);

  const handleExportObsidian = async () => {
    if (!selectedConceptId || exporting) return;
    setExporting(true);
    try {
      const result = await exportConceptToObsidian(selectedConceptId);
      const blob = new Blob([result.content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
      setExported(true);
      setTimeout(() => setExported(false), 2000);
    } catch (e) {
      console.error("Export failed:", e);
    } finally {
      setExporting(false);
    }
  };

  if (!conceptPanelOpen) return null;

  // Empty state when panel is open but no concept selected
  if (!selectedConceptId) {
    return (
      <motion.aside
        initial={{ opacity: 0, x: 16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.25 }}
        className="w-[320px] flex-shrink-0 border-l border-border bg-surface/40 flex flex-col h-full overflow-hidden"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-sm font-semibold text-foreground" style={{ fontFamily: f.display }}>
            {t.conceptDetail}
          </span>
          <button
            onClick={() => useChatStore.getState().setConceptPanelOpen(false)}
            className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex flex-col items-center justify-center flex-1 px-6 text-center">
          <div className="w-16 h-16 rounded-full bg-accent-gold-dim/30 flex items-center justify-center mb-4">
            <Compass size={28} className="text-accent-gold/40" />
          </div>
          <p className="text-sm text-text-secondary mb-1">{t.noConceptSelected}</p>
          <p className="text-xs text-text-tertiary">
            {t.clickBadgeHint}
          </p>
        </div>
      </motion.aside>
    );
  }

  const confidenceLabel = (c: number) => {
    if (c > 0.85) return { text: t.wellEstablished, icon: CheckCircle2, color: "text-accent-green", barColor: "var(--accent-green)" };
    if (c >= 0.6) return { text: t.likelyAccurate, icon: Shield, color: "text-accent-blue", barColor: "var(--accent-blue)" };
    if (c >= 0.4) return { text: t.needsMoreEvidence, icon: AlertTriangle, color: "text-accent-amber", barColor: "var(--accent-amber)" };
    return { text: t.emerging, icon: TrendingUp, color: "text-text-tertiary", barColor: "var(--text-tertiary)" };
  };

  return (
    <motion.aside
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.25 }}
      className="w-[320px] flex-shrink-0 border-l border-border bg-surface/40 flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-sm font-semibold text-foreground" style={{ fontFamily: f.display }}>
          {t.conceptDetail}
        </span>
        <div className="flex items-center gap-1">
          {concept && (
            <button
              onClick={handleExportObsidian}
              disabled={exporting}
              className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-accent-gold transition-colors"
              title={locale === "he" ? "ייצוא ל-Obsidian" : "Export to Obsidian"}
            >
              {exported ? <Check size={16} className="text-accent-green" /> : <Download size={16} />}
            </button>
          )}
          <button
            onClick={() => setSelectedConceptId(null)}
            className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <div className="flex gap-1.5">
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-1" />
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-2" />
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-3" />
            </div>
            <span className="thinking-text">{t.loadingConcept}</span>
          </div>
        ) : concept ? (
          <>
            {/* Name + Type — exhibit card style */}
            <div className="exhibit-card">
              <h2
                className="text-lg font-bold text-foreground mb-2"
                style={{ fontFamily: f.display }}
              >
                {concept.name}
              </h2>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-accent-gold-dim text-accent-gold">
                  {concept.type}
                </span>
                {concept.trend && concept.trend !== "stable" && (
                  <span className="flex items-center gap-1 text-[10px] text-text-secondary">
                    <TrendingUp size={10} />
                    {concept.trend}
                  </span>
                )}
              </div>
            </div>

            {/* Definition */}
            {concept.definition && (
              <div>
                <p className="text-sm text-text-secondary" style={{ lineHeight: '1.75' }}>
                  {concept.definition}
                </p>
              </div>
            )}

            {/* Confidence — bar visualization */}
            <div className="space-y-2">
              {(() => {
                const c = confidenceLabel(concept.confidence);
                return (
                  <>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <c.icon size={14} className={c.color} />
                        <span className={`text-xs ${c.color}`}>{c.text}</span>
                      </div>
                      <span className="text-[10px] text-text-tertiary">
                        {(concept.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="confidence-bar">
                      <div
                        className="confidence-bar-fill"
                        style={{
                          width: `${concept.confidence * 100}%`,
                          background: c.barColor,
                        }}
                      />
                    </div>
                  </>
                );
              })()}
            </div>

            {/* Papers count */}
            {concept.paper_count > 0 && (
              <div className="flex items-center gap-2">
                <BookOpen size={14} className="text-accent-blue" />
                <span className="text-xs text-text-secondary">
                  {t.referencedIn} {concept.paper_count} {t.papers}
                </span>
              </div>
            )}

            {/* Key Papers */}
            {concept.key_papers && concept.key_papers.length > 0 && (
              <section>
                <h3 className="section-header flex items-center gap-2 mb-3">
                  <BookOpen size={12} />
                  {locale === "he" ? "מאמרים מרכזיים" : "Key Papers"}
                </h3>
                <div className="space-y-2">
                  {concept.key_papers.map((paper) => (
                    <div
                      key={paper.id}
                      className="px-3 py-2 rounded-lg bg-surface-sunken text-left"
                    >
                      <p className="text-xs text-foreground leading-relaxed line-clamp-2">
                        {paper.title}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-text-tertiary">
                        {paper.authors?.[0]?.name && (
                          <span>{paper.authors[0].name}{paper.authors.length > 1 ? " et al." : ""}</span>
                        )}
                        {paper.publication_year && <span>{paper.publication_year}</span>}
                        {paper.cited_by_count > 0 && (
                          <span>{paper.cited_by_count} {t.citations}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Key Claims */}
            {concept.key_claims && concept.key_claims.length > 0 && (
              <section>
                <h3 className="section-header flex items-center gap-2 mb-3">
                  <Shield size={12} />
                  {locale === "he" ? "טענות מרכזיות" : "Key Claims"}
                </h3>
                <div className="space-y-1.5">
                  {concept.key_claims.map((claim, i) => (
                    <div
                      key={i}
                      className="px-3 py-2 rounded-lg bg-surface-sunken"
                    >
                      <p className="text-xs text-text-secondary leading-relaxed line-clamp-3">
                        {claim.claim_text}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-text-tertiary">
                        <span className="capitalize">{claim.evidence_type}</span>
                        <span className="capitalize">{claim.strength}</span>
                        <span>{(claim.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Related Concepts — color-coded by relationship type, with explanations */}
            {neighbors && neighbors.related && neighbors.related.length > 0 && (
              <section>
                <h3 className="section-header flex items-center gap-2 mb-3">
                  <GitBranch size={12} />
                  {t.connectedConcepts}
                </h3>
                <div className="space-y-1.5">
                  {neighbors.related.map((rel, i) => (
                    <button
                      key={i}
                      onClick={() => setSelectedConceptId(rel.concept.id)}
                      className={`w-full px-3 py-2.5 rounded-lg
                        bg-surface-sunken hover:bg-surface-hover
                        border-l-2 ${REL_COLORS[rel.relationship_type] || "border-l-border"}
                        text-left transition-all duration-150 group`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-sm text-foreground group-hover:text-accent-gold transition-colors">
                            {rel.concept.name}
                          </span>
                          <span className="block text-[10px] text-text-tertiary mt-0.5">
                            {rel.relationship_type.replace(/_/g, " ").toLowerCase()}
                          </span>
                        </div>
                        <span className="text-[10px] text-text-tertiary">
                          {(rel.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      {/* WHY this connection exists */}
                      {rel.explanation && (
                        <p className="text-[10px] text-text-tertiary leading-relaxed mt-1 italic">
                          {rel.explanation}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Community Summaries */}
            <ConceptSummaries conceptId={concept.id} researcherId={researcherId} />

            {/* Discussions */}
            <DiscussionThread targetType="concept" targetId={concept.id} researcherId={researcherId} />
          </>
        ) : (
          <div className="flex flex-col items-center py-12 text-center">
            <p className="text-sm text-text-secondary">{t.conceptNotFound}</p>
          </div>
        )}
      </div>
    </motion.aside>
  );
}
