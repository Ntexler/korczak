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
} from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { getConceptDetail, getConceptNeighbors } from "@/lib/api";

interface ConceptData {
  id: string;
  name: string;
  type: string;
  definition?: string;
  paper_count: number;
  trend: string;
  confidence: number;
}

interface NeighborData {
  concept: ConceptData;
  related: {
    concept: { id: string; name: string; type: string };
    relationship_type: string;
    confidence: number;
  }[];
}

export default function ConceptDetail() {
  const { selectedConceptId, conceptPanelOpen, setSelectedConceptId } =
    useChatStore();
  const [concept, setConcept] = useState<ConceptData | null>(null);
  const [neighbors, setNeighbors] = useState<NeighborData | null>(null);
  const [loading, setLoading] = useState(false);

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

  if (!conceptPanelOpen || !selectedConceptId) return null;

  const confidenceLabel = (c: number) => {
    if (c > 0.85) return { text: "Well-established", icon: CheckCircle2, color: "text-accent-green" };
    if (c >= 0.6) return { text: "Likely accurate", icon: Shield, color: "text-accent-amber" };
    return { text: "Needs more evidence", icon: AlertTriangle, color: "text-text-secondary" };
  };

  return (
    <motion.aside
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.25 }}
      className="w-[320px] flex-shrink-0 border-l border-border bg-surface/50 flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-sm font-semibold text-foreground truncate">
          Concept Detail
        </span>
        <button
          onClick={() => setSelectedConceptId(null)}
          className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-1" />
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-2" />
              <span className="w-2 h-2 bg-accent-gold rounded-full dot-bounce-3" />
            </div>
          </div>
        ) : concept ? (
          <>
            {/* Name + Type */}
            <div>
              <h2
                className="text-lg font-bold text-foreground mb-1"
                style={{ fontFamily: "var(--font-serif)" }}
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
                <p className="text-sm text-text-secondary leading-relaxed">
                  {concept.definition}
                </p>
              </div>
            )}

            {/* Confidence */}
            <div>
              {(() => {
                const c = confidenceLabel(concept.confidence);
                return (
                  <div className="flex items-center gap-2">
                    <c.icon size={14} className={c.color} />
                    <span className={`text-xs ${c.color}`}>{c.text}</span>
                    <span className="text-[10px] text-text-secondary">
                      ({(concept.confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                );
              })()}
            </div>

            {/* Papers count */}
            {concept.paper_count > 0 && (
              <div className="flex items-center gap-2">
                <BookOpen size={14} className="text-accent-blue" />
                <span className="text-xs text-text-secondary">
                  Referenced in {concept.paper_count} papers
                </span>
              </div>
            )}

            {/* Related Concepts */}
            {neighbors && neighbors.related && neighbors.related.length > 0 && (
              <section>
                <h3 className="flex items-center gap-2 text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
                  <GitBranch size={12} />
                  Connected Concepts
                </h3>
                <div className="space-y-1.5">
                  {neighbors.related.map((rel, i) => (
                    <button
                      key={i}
                      onClick={() => setSelectedConceptId(rel.concept.id)}
                      className="flex items-center justify-between w-full px-3 py-2 rounded-lg
                        bg-background/50 hover:bg-surface-hover
                        text-left transition-colors group"
                    >
                      <div>
                        <span className="text-sm text-foreground group-hover:text-accent-gold transition-colors">
                          {rel.concept.name}
                        </span>
                        <span className="block text-[10px] text-text-secondary">
                          {rel.relationship_type.replace(/_/g, " ").toLowerCase()}
                        </span>
                      </div>
                      <span className="text-[10px] text-text-secondary">
                        {(rel.confidence * 100).toFixed(0)}%
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </>
        ) : (
          <p className="text-sm text-text-secondary text-center py-8">
            Concept not found
          </p>
        )}
      </div>
    </motion.aside>
  );
}
