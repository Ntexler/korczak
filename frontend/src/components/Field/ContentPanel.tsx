"use client";

import { useEffect, useState } from "react";
import {
  BookOpen, ArrowDown, ArrowUp, FileText, Link2, CheckCircle,
  HelpCircle, ChevronDown, ChevronUp, MessageCircle, Quote, Lightbulb,
} from "lucide-react";
import ConceptTooltip from "./ConceptTooltip";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Paper {
  id: string;
  title: string;
  authors?: string;
  year?: number;
  cited_by_count?: number;
  abstract?: string;
  doi?: string;
}

interface Claim {
  id: string;
  claim_text: string;
  evidence_type?: string;
  strength?: string;
  paper_title?: string;
}

interface Connection {
  id: string;
  name: string;
  relationship?: string;
  explanation?: string;
  confidence?: number;
}

interface ConceptData {
  concept_id: string;
  name: string;
  type?: string;
  definition?: string;
  simple_explanation?: string;
  paper_count?: number;
  key_papers?: Paper[];
  key_claims?: Claim[];
  connections?: Connection[];
  explain_simpler_prompt?: string;
  go_deeper_prompt?: string;
}

interface FieldOverview {
  name: string;
  description?: string;
  paper_count?: number;
  concept_count?: number;
  top_concepts?: { id: string; name: string; type?: string; paper_count?: number }[];
}

interface ContentPanelProps {
  conceptId: string | null;
  field: string;
  locale: string;
  onSend: (text: string) => void;
}

function renderTextWithConcepts(
  text: string,
  concepts: { id: string; name: string }[],
  onSelect: (id: string) => void
): React.ReactNode[] {
  if (!concepts.length) return [text];
  const sorted = [...concepts].sort((a, b) => b.name.length - a.name.length);
  const pattern = sorted
    .map((c) => c.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const regex = new RegExp(`(${pattern})`, "gi");
  const parts = text.split(regex);

  return parts.map((part, i) => {
    const match = sorted.find(
      (c) => c.name.toLowerCase() === part.toLowerCase()
    );
    if (match) {
      return (
        <ConceptTooltip
          key={`${match.id}-${i}`}
          conceptId={match.id}
          name={part}
          onSelect={onSelect}
        />
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function ContentPanel({
  conceptId,
  field,
  locale,
  onSend,
}: ContentPanelProps) {
  const [concept, setConcept] = useState<ConceptData | null>(null);
  const [overview, setOverview] = useState<FieldOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState<string | null>(conceptId);
  const [expandedPaper, setExpandedPaper] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<"understood" | "more" | null>(null);

  useEffect(() => { setSelectedConcept(conceptId); }, [conceptId]);

  // Fetch concept with full data (explanation + papers + claims + connections)
  useEffect(() => {
    if (!selectedConcept) { setConcept(null); return; }
    let cancelled = false;
    setLoading(true);
    setFeedback(null);

    (async () => {
      try {
        // Fetch explanation
        const explainRes = await fetch(
          `${API_BASE}/features/explain/${encodeURIComponent(selectedConcept)}?locale=${locale}`
        );
        let data: any = {};
        if (explainRes.ok) data = await explainRes.json();

        // Fetch full concept context (papers, claims, neighbors)
        try {
          const contextRes = await fetch(
            `${API_BASE}/graph/concepts/${encodeURIComponent(selectedConcept)}/context`
          );
          if (contextRes.ok) {
            const ctx = await contextRes.json();
            data.key_papers = ctx.key_papers || data.key_papers || [];
            data.key_claims = ctx.key_claims || [];
            data.connections = ctx.neighbors?.map((n: any) => ({
              id: n.concept?.id || n.id,
              name: n.concept?.name || n.name,
              relationship: n.relationship_type,
              explanation: n.explanation,
              confidence: n.confidence,
            })) || [];
          }
        } catch { /* non-critical */ }

        if (!cancelled) setConcept(data);
      } catch {
        if (!cancelled) setConcept(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedConcept, locale]);

  // Fetch field overview
  useEffect(() => {
    if (selectedConcept) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/features/fields/${encodeURIComponent(field)}/concepts?limit=30`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setOverview({
            name: field,
            concept_count: data.total,
            top_concepts: data.concepts,
          });
        }
      } catch { /* non-critical */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [field, selectedConcept]);

  const handleSelectConcept = (id: string) => setSelectedConcept(id);

  const handleFeedback = (type: "understood" | "more") => {
    setFeedback(type);
    if (type === "more" && concept) {
      onSend(
        locale === "he"
          ? `תסביר לי יותר לעומק את ${concept.name}`
          : `Explain ${concept.name} in more depth, with examples`
      );
    }
  };

  const allConcepts: { id: string; name: string }[] = [
    ...(concept?.connections?.map((c) => ({ id: c.id, name: c.name })) ?? []),
    ...(overview?.top_concepts?.map((c) => ({ id: c.id, name: c.name })) ?? []),
  ];

  const he = locale === "he";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        {he ? "טוען..." : "Loading..."}
      </div>
    );
  }

  // ── Field Overview ──
  if (!selectedConcept) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <h2 className="text-2xl font-bold text-foreground mb-2">{field}</h2>
        <p className="text-text-secondary text-sm mb-6">
          {he
            ? `${overview?.concept_count || 0} קונספטים במאגר. לחץ על אחד כדי להתחיל ללמוד.`
            : `${overview?.concept_count || 0} concepts in the knowledge base. Click one to start learning.`
          }
        </p>

        {overview?.top_concepts && overview.top_concepts.length > 0 && (
          <div className="space-y-2">
            {overview.top_concepts.map((c) => (
              <button
                key={c.id}
                onClick={() => handleSelectConcept(c.id)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-lg
                  bg-surface border border-border hover:border-accent-gold/40
                  text-left transition-all group"
              >
                <div>
                  <span className="text-sm text-foreground group-hover:text-accent-gold transition-colors font-medium">
                    {c.name}
                  </span>
                  {c.type && (
                    <span className="text-[10px] text-text-tertiary ml-2 uppercase">{c.type}</span>
                  )}
                </div>
                {c.paper_count != null && c.paper_count > 0 && (
                  <span className="text-[10px] text-text-tertiary flex items-center gap-1">
                    <FileText size={10} /> {c.paper_count}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Concept Lesson View ──
  if (!concept) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        {he ? "לא נמצא" : "Concept not found"}
      </div>
    );
  }

  const explanation = concept.simple_explanation || concept.definition || "";

  return (
    <div className="h-full overflow-y-auto">
      {/* Lesson header */}
      <div className="px-6 pt-6 pb-4 border-b border-border">
        <div className="flex items-center gap-2 text-[10px] text-text-tertiary uppercase tracking-wider mb-2">
          <BookOpen size={11} />
          {he ? "שיעור" : "Lesson"} — {field}
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-1">{concept.name}</h2>
        {concept.type && (
          <span className="text-xs text-accent-gold bg-accent-gold/10 px-2 py-0.5 rounded-full">
            {concept.type}
          </span>
        )}
      </div>

      <div className="px-6 py-5 space-y-6">

        {/* Main explanation */}
        {explanation && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
              <Lightbulb size={12} className="text-accent-gold" />
              {he ? "הסבר פשוט" : "Simple Explanation"}
            </h3>
            <div className="text-sm text-text-secondary leading-relaxed bg-surface-sunken rounded-xl p-4 border border-border/50">
              {renderTextWithConcepts(explanation, allConcepts, handleSelectConcept)}
            </div>
          </section>
        )}

        {/* Feedback buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => handleFeedback("understood")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm transition-all ${
              feedback === "understood"
                ? "bg-green-500/15 text-green-400 border border-green-500/30"
                : "bg-surface border border-border text-text-secondary hover:border-green-500/30 hover:text-green-400"
            }`}
          >
            <CheckCircle size={14} />
            {he ? "הבנתי" : "Got it"}
          </button>
          <button
            onClick={() => handleFeedback("more")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm transition-all ${
              feedback === "more"
                ? "bg-accent-gold/15 text-accent-gold border border-accent-gold/30"
                : "bg-surface border border-border text-text-secondary hover:border-accent-gold/30 hover:text-accent-gold"
            }`}
          >
            <HelpCircle size={14} />
            {he ? "תסביר עוד" : "Explain more"}
          </button>
          <button
            onClick={() => onSend(concept.explain_simpler_prompt || `Explain "${concept.name}" like I'm in high school`)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm
              bg-surface border border-border text-text-secondary
              hover:border-accent-gold/30 hover:text-accent-gold transition-all"
          >
            <ArrowDown size={14} />
            {he ? "פשט לי" : "Simpler"}
          </button>
          <button
            onClick={() => onSend(concept.go_deeper_prompt || `Go deeper on "${concept.name}"`)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm
              bg-surface border border-border text-text-secondary
              hover:border-accent-gold/30 hover:text-accent-gold transition-all"
          >
            <ArrowUp size={14} />
            {he ? "העמק" : "Go deeper"}
          </button>
        </div>

        {/* Key Claims */}
        {concept.key_claims && concept.key_claims.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
              <Quote size={12} className="text-accent-gold" />
              {he ? "טענות עיקריות" : "Key Claims"}
            </h3>
            <div className="space-y-2">
              {concept.key_claims.map((claim, i) => (
                <div
                  key={claim.id || i}
                  className="px-4 py-3 rounded-lg bg-surface border border-border/50"
                >
                  <p className="text-sm text-foreground leading-relaxed">
                    "{claim.claim_text}"
                  </p>
                  <div className="flex items-center gap-3 mt-2 text-[10px] text-text-tertiary">
                    {claim.evidence_type && (
                      <span className="px-1.5 py-0.5 rounded bg-surface-sunken">{claim.evidence_type}</span>
                    )}
                    {claim.strength && (
                      <span className={`px-1.5 py-0.5 rounded ${
                        claim.strength === "strong" ? "bg-green-500/10 text-green-400" :
                        claim.strength === "moderate" ? "bg-yellow-500/10 text-yellow-400" :
                        "bg-red-500/10 text-red-400"
                      }`}>{claim.strength}</span>
                    )}
                    {claim.paper_title && (
                      <span className="truncate max-w-[200px]">from: {claim.paper_title}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Key Papers — expandable with abstracts */}
        {concept.key_papers && concept.key_papers.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
              <FileText size={12} className="text-accent-gold" />
              {he ? "מאמרים מרכזיים" : "Key Papers"}
            </h3>
            <div className="space-y-2">
              {concept.key_papers.map((paper) => (
                <div key={paper.id} className="rounded-lg bg-surface border border-border/50 overflow-hidden">
                  <button
                    onClick={() => setExpandedPaper(expandedPaper === paper.id ? null : paper.id)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-surface-hover transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-foreground font-medium leading-snug">
                        {paper.title}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-text-tertiary">
                        {paper.authors && <span className="truncate max-w-[200px]">{paper.authors}</span>}
                        {paper.year && <span>({paper.year})</span>}
                        {paper.cited_by_count != null && paper.cited_by_count > 0 && (
                          <span>{paper.cited_by_count} citations</span>
                        )}
                      </div>
                    </div>
                    {expandedPaper === paper.id
                      ? <ChevronUp size={14} className="text-text-tertiary flex-shrink-0" />
                      : <ChevronDown size={14} className="text-text-tertiary flex-shrink-0" />
                    }
                  </button>

                  {expandedPaper === paper.id && (
                    <div className="px-4 pb-4 border-t border-border/30">
                      {paper.abstract ? (
                        <div className="mt-3">
                          <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1.5">Abstract</div>
                          <p className="text-xs text-text-secondary leading-relaxed">
                            {paper.abstract}
                          </p>
                        </div>
                      ) : (
                        <p className="text-xs text-text-tertiary mt-3 italic">
                          {he ? "אין אבסטרקט זמין" : "No abstract available"}
                        </p>
                      )}
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={() => onSend(
                            he ? `תסביר לי את המאמר "${paper.title}"` : `Explain the paper "${paper.title}"`
                          )}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded text-[10px]
                            bg-accent-gold/10 text-accent-gold hover:bg-accent-gold/20 transition-colors"
                        >
                          <MessageCircle size={10} /> {he ? "הסבר על המאמר" : "Explain this paper"}
                        </button>
                        {paper.doi && (
                          <a
                            href={paper.doi}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded text-[10px]
                              bg-surface-sunken text-text-tertiary hover:text-text-secondary transition-colors"
                          >
                            <Link2 size={10} /> DOI
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Connections */}
        {concept.connections && concept.connections.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
              <Link2 size={12} className="text-accent-gold" />
              {he ? "קשרים לנושאים אחרים" : "Connections"}
            </h3>
            <div className="space-y-1.5">
              {concept.connections.map((conn) => (
                <button
                  key={conn.id}
                  onClick={() => handleSelectConcept(conn.id)}
                  className="w-full flex items-start gap-3 px-4 py-2.5 rounded-lg
                    bg-surface border border-border/50 hover:border-accent-gold/30
                    text-left transition-all group"
                >
                  <div className="min-w-0 flex-1">
                    <span className="text-sm text-foreground group-hover:text-accent-gold transition-colors">
                      {conn.name}
                    </span>
                    {conn.relationship && (
                      <span className="text-[10px] text-text-tertiary ml-2">
                        {conn.relationship.replace(/_/g, " ").toLowerCase()}
                      </span>
                    )}
                    {conn.explanation && (
                      <p className="text-[10px] text-text-tertiary mt-0.5 leading-relaxed">
                        {conn.explanation.slice(0, 120)}
                        {conn.explanation.length > 120 ? "..." : ""}
                      </p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Ask about this concept */}
        <section className="pb-4">
          <button
            onClick={() => onSend(
              he
                ? `ספר לי עוד על ${concept.name} בהקשר של ${field}`
                : `Tell me more about ${concept.name} in the context of ${field}`
            )}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg
              bg-accent-gold/10 border border-accent-gold/20 text-accent-gold text-sm
              hover:bg-accent-gold/20 transition-colors"
          >
            <MessageCircle size={14} />
            {he ? `שוחח עם קורצאק על ${concept.name}` : `Chat with Korczak about ${concept.name}`}
          </button>
        </section>
      </div>
    </div>
  );
}
