"use client";

import { useEffect, useState, useCallback } from "react";
import {
  BookOpen, ArrowDown, ArrowUp, FileText, Link2, CheckCircle,
  HelpCircle, ChevronDown, ChevronUp, MessageCircle, Quote, Lightbulb,
  Shield, AlertTriangle, ThumbsUp, ThumbsDown, Brain, SlidersHorizontal,
  Eye, EyeOff, Sparkles,
} from "lucide-react";
import ConceptTooltip from "./ConceptTooltip";
import { getClaimEvidenceMap, explainAtDepth, generateQuiz } from "@/lib/api";

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

interface EvidenceClaim {
  id: string;
  claim_text: string;
  evidence_type?: string;
  strength?: string;
  confidence: number;
  support_count: number;
  contradict_count: number;
  status: string;
  paper_citations: number;
  contradictions: string[];
}

interface QuizQuestion {
  type: string;
  concept_id: string;
  question: string;
  hint: string;
  answer: string;
  difficulty: number;
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

const DEPTH_LABELS = [
  { depth: 1, label: "High School", label_he: "תיכון", emoji: "🏫" },
  { depth: 2, label: "Undergrad", label_he: "תואר ראשון", emoji: "🎓" },
  { depth: 3, label: "Advanced", label_he: "מתקדם", emoji: "📚" },
  { depth: 4, label: "Graduate", label_he: "תואר שני", emoji: "🔬" },
  { depth: 5, label: "Expert", label_he: "מומחה", emoji: "🧠" },
];

const STATUS_CONFIG: Record<string, { icon: any; color: string; bg: string; label: string; label_he: string }> = {
  well_supported: { icon: ThumbsUp, color: "text-green-400", bg: "bg-green-500/10", label: "Well Supported", label_he: "נתמך היטב" },
  supported: { icon: Shield, color: "text-blue-400", bg: "bg-blue-500/10", label: "Supported", label_he: "נתמך" },
  debated: { icon: AlertTriangle, color: "text-amber-400", bg: "bg-amber-500/10", label: "Actively Debated", label_he: "שנוי במחלוקת" },
  challenged: { icon: ThumbsDown, color: "text-red-400", bg: "bg-red-500/10", label: "Challenged", label_he: "מאותגר" },
  single_source: { icon: FileText, color: "text-text-tertiary", bg: "bg-surface-sunken", label: "Single Source", label_he: "מקור יחיד" },
};

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

  // New: depth slider state
  const [depth, setDepth] = useState(2);
  const [depthExplanation, setDepthExplanation] = useState<string | null>(null);
  const [depthLoading, setDepthLoading] = useState(false);

  // New: evidence map state
  const [evidenceClaims, setEvidenceClaims] = useState<EvidenceClaim[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [expandedContradiction, setExpandedContradiction] = useState<string | null>(null);

  // New: quiz state
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[]>([]);
  const [quizActive, setQuizActive] = useState(false);
  const [quizIndex, setQuizIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [quizLoading, setQuizLoading] = useState(false);

  useEffect(() => { setSelectedConcept(conceptId); }, [conceptId]);

  // Fetch concept
  useEffect(() => {
    if (!selectedConcept) { setConcept(null); return; }
    let cancelled = false;
    setLoading(true);
    setFeedback(null);
    setDepthExplanation(null);
    setEvidenceClaims([]);
    setQuizActive(false);

    (async () => {
      try {
        const explainRes = await fetch(
          `${API_BASE}/features/explain/${encodeURIComponent(selectedConcept)}?locale=${locale}`
        );
        let data: any = {};
        if (explainRes.ok) data = await explainRes.json();

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

  // Fetch evidence map when concept loaded
  useEffect(() => {
    if (!concept?.concept_id) return;
    let cancelled = false;
    setEvidenceLoading(true);
    getClaimEvidenceMap(concept.concept_id)
      .then((res) => { if (!cancelled) setEvidenceClaims(res.claims || []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setEvidenceLoading(false); });
    return () => { cancelled = true; };
  }, [concept?.concept_id]);

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

  const handleDepthChange = useCallback(async (newDepth: number) => {
    if (!concept?.concept_id || depthLoading) return;
    setDepth(newDepth);
    setDepthLoading(true);
    try {
      const result = await explainAtDepth(concept.concept_id, newDepth, locale);
      setDepthExplanation(result.explanation);
    } catch {
      setDepthExplanation(null);
    } finally {
      setDepthLoading(false);
    }
  }, [concept?.concept_id, locale, depthLoading]);

  const handleStartQuiz = async () => {
    if (quizLoading) return;
    setQuizLoading(true);
    try {
      const ids = concept?.concept_id ? [concept.concept_id] : undefined;
      const result = await generateQuiz(
        ids ? undefined : field,
        ids,
        5,
        locale,
      );
      if (result.questions?.length) {
        setQuizQuestions(result.questions);
        setQuizIndex(0);
        setShowAnswer(false);
        setQuizActive(true);
      }
    } catch { /* ignore */ }
    finally { setQuizLoading(false); }
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
        <p className="text-text-secondary text-sm mb-4">
          {he
            ? `${overview?.concept_count || 0} קונספטים במאגר. לחץ על אחד כדי להתחיל ללמוד.`
            : `${overview?.concept_count || 0} concepts in the knowledge base. Click one to start learning.`
          }
        </p>

        {/* Quiz button for field */}
        <button
          onClick={handleStartQuiz}
          disabled={quizLoading}
          className="flex items-center gap-2 px-4 py-2.5 mb-6 rounded-lg
            bg-accent-gold/10 border border-accent-gold/20 text-accent-gold text-sm
            hover:bg-accent-gold/20 transition-colors disabled:opacity-50"
        >
          <Brain size={16} />
          {quizLoading ? (he ? "מכין..." : "Generating...") : (he ? "בחן אותי על התחום" : "Quiz me on this field")}
        </button>

        {/* Quiz mode */}
        {quizActive && quizQuestions.length > 0 && (
          <QuizCard
            question={quizQuestions[quizIndex]}
            index={quizIndex}
            total={quizQuestions.length}
            showAnswer={showAnswer}
            onReveal={() => setShowAnswer(true)}
            onNext={() => { setQuizIndex((i) => i + 1); setShowAnswer(false); }}
            onClose={() => setQuizActive(false)}
            onSend={onSend}
            he={he}
          />
        )}

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

  const displayExplanation = depthExplanation || concept.simple_explanation || concept.definition || "";
  const currentDepthLabel = DEPTH_LABELS.find((d) => d.depth === depth);

  return (
    <div className="h-full overflow-y-auto">
      {/* Lesson header */}
      <div className="px-6 pt-6 pb-4 border-b border-border">
        <div className="flex items-center gap-2 text-[10px] text-text-tertiary uppercase tracking-wider mb-2">
          <BookOpen size={11} />
          {he ? "שיעור" : "Lesson"} — {field}
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-1">{concept.name}</h2>
        <div className="flex items-center gap-2">
          {concept.type && (
            <span className="text-xs text-accent-gold bg-accent-gold/10 px-2 py-0.5 rounded-full">
              {concept.type}
            </span>
          )}
          {concept.paper_count != null && concept.paper_count > 0 && (
            <span className="text-[10px] text-text-tertiary flex items-center gap-1">
              <FileText size={10} /> {concept.paper_count} {he ? "מאמרים" : "papers"}
            </span>
          )}
        </div>
      </div>

      <div className="px-6 py-5 space-y-6">

        {/* ── Depth Slider ── */}
        <section className="bg-surface-sunken rounded-xl p-4 border border-border/50">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-1.5">
              <SlidersHorizontal size={12} className="text-accent-gold" />
              {he ? "רמת עומק" : "Depth Level"}
            </h3>
            <span className="text-xs text-accent-gold font-medium">
              {he ? currentDepthLabel?.label_he : currentDepthLabel?.label}
            </span>
          </div>

          {/* Slider */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-text-tertiary">{he ? "פשוט" : "Simple"}</span>
            <input
              type="range"
              min={1}
              max={5}
              value={depth}
              onChange={(e) => handleDepthChange(Number(e.target.value))}
              className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer
                bg-border accent-accent-gold
                [&::-webkit-slider-thumb]:appearance-none
                [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent-gold
                [&::-webkit-slider-thumb]:shadow-md"
            />
            <span className="text-[10px] text-text-tertiary">{he ? "מומחה" : "Expert"}</span>
          </div>

          {/* Depth tick marks */}
          <div className="flex justify-between mt-1 px-1">
            {DEPTH_LABELS.map((d) => (
              <button
                key={d.depth}
                onClick={() => handleDepthChange(d.depth)}
                className={`text-[9px] transition-colors ${
                  depth === d.depth ? "text-accent-gold font-medium" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                {d.depth}
              </button>
            ))}
          </div>
        </section>

        {/* Main explanation */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
            <Lightbulb size={12} className="text-accent-gold" />
            {he ? "הסבר" : "Explanation"}
            {depthLoading && <span className="text-[10px] text-accent-gold animate-pulse ml-1">{he ? "טוען..." : "loading..."}</span>}
          </h3>
          <div className="text-sm text-text-secondary leading-relaxed bg-surface-sunken rounded-xl p-4 border border-border/50">
            {depthLoading ? (
              <div className="flex items-center gap-2 text-text-tertiary">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-accent-gold rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-accent-gold rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-accent-gold rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
                {he ? "מכין הסבר..." : "Generating explanation..."}
              </div>
            ) : (
              renderTextWithConcepts(displayExplanation, allConcepts, handleSelectConcept)
            )}
          </div>
        </section>

        {/* Feedback buttons */}
        <div className="flex flex-wrap gap-2">
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
            onClick={handleStartQuiz}
            disabled={quizLoading}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm
              bg-surface border border-border text-text-secondary
              hover:border-accent-gold/30 hover:text-accent-gold transition-all disabled:opacity-50"
          >
            <Brain size={14} />
            {quizLoading ? (he ? "מכין..." : "...") : (he ? "בחן אותי" : "Quiz me")}
          </button>
        </div>

        {/* ── Quiz Mode ── */}
        {quizActive && quizQuestions.length > 0 && (
          <QuizCard
            question={quizQuestions[quizIndex]}
            index={quizIndex}
            total={quizQuestions.length}
            showAnswer={showAnswer}
            onReveal={() => setShowAnswer(true)}
            onNext={() => { setQuizIndex((i) => i + 1); setShowAnswer(false); }}
            onClose={() => setQuizActive(false)}
            onSend={onSend}
            he={he}
          />
        )}

        {/* ── Claims with Evidence Indicators ── */}
        {evidenceClaims.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3 flex items-center gap-1.5">
              <Quote size={12} className="text-accent-gold" />
              {he ? "טענות עיקריות" : "Key Claims"}
              <span className="text-[10px] font-normal text-text-tertiary ml-1">
                ({he ? "עם מפת ראיות" : "with evidence map"})
              </span>
            </h3>
            <div className="space-y-2">
              {evidenceClaims.map((claim) => {
                const config = STATUS_CONFIG[claim.status] || STATUS_CONFIG.single_source;
                const StatusIcon = config.icon;
                const hasContradictions = claim.contradictions.length > 0;
                const isExpanded = expandedContradiction === claim.id;

                return (
                  <div
                    key={claim.id}
                    className="rounded-lg bg-surface border border-border/50 overflow-hidden"
                  >
                    <div className="px-4 py-3">
                      <p className="text-sm text-foreground leading-relaxed">
                        &ldquo;{claim.claim_text}&rdquo;
                      </p>

                      {/* Evidence indicator bar */}
                      <div className="flex items-center gap-3 mt-2.5 flex-wrap">
                        {/* Status badge */}
                        <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${config.bg} ${config.color}`}>
                          <StatusIcon size={10} />
                          {he ? config.label_he : config.label}
                        </span>

                        {/* Support/contradict counts */}
                        {claim.support_count > 0 && (
                          <span className="flex items-center gap-1 text-[10px] text-green-400">
                            <ThumbsUp size={9} /> {claim.support_count} {he ? "תומכים" : "support"}
                          </span>
                        )}
                        {claim.contradict_count > 0 && (
                          <span className="flex items-center gap-1 text-[10px] text-red-400">
                            <ThumbsDown size={9} /> {claim.contradict_count} {he ? "סותרים" : "contradict"}
                          </span>
                        )}

                        {claim.evidence_type && (
                          <span className="text-[10px] text-text-tertiary px-1.5 py-0.5 rounded bg-surface-sunken">
                            {claim.evidence_type}
                          </span>
                        )}
                        {claim.strength && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                            claim.strength === "strong" ? "bg-green-500/10 text-green-400" :
                            claim.strength === "moderate" ? "bg-yellow-500/10 text-yellow-400" :
                            "bg-red-500/10 text-red-400"
                          }`}>{claim.strength}</span>
                        )}
                      </div>

                      {/* Expand contradictions */}
                      {hasContradictions && (
                        <button
                          onClick={() => setExpandedContradiction(isExpanded ? null : claim.id)}
                          className="flex items-center gap-1 mt-2 text-[10px] text-red-400 hover:text-red-300 transition-colors"
                        >
                          {isExpanded ? <EyeOff size={10} /> : <Eye size={10} />}
                          {he ? `ראה ${claim.contradictions.length} טענות סותרות` : `See ${claim.contradictions.length} contradicting claims`}
                        </button>
                      )}
                    </div>

                    {/* Contradicting claims expanded */}
                    {isExpanded && hasContradictions && (
                      <div className="px-4 pb-3 border-t border-border/30">
                        <div className="mt-2 space-y-1.5">
                          {claim.contradictions.map((ct, i) => (
                            <div key={i} className="flex gap-2 px-3 py-2 rounded bg-red-500/5 border border-red-500/10">
                              <ThumbsDown size={10} className="text-red-400 mt-1 shrink-0" />
                              <p className="text-xs text-text-secondary leading-relaxed">&ldquo;{ct}&rdquo;</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Fallback: original claims if no evidence map */}
        {evidenceClaims.length === 0 && !evidenceLoading && concept.key_claims && concept.key_claims.length > 0 && (
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
                    &ldquo;{claim.claim_text}&rdquo;
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
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Key Papers */}
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


// ─── Quiz Card Component ────────────────────────────────────────────────────

function QuizCard({
  question,
  index,
  total,
  showAnswer,
  onReveal,
  onNext,
  onClose,
  onSend,
  he,
}: {
  question: QuizQuestion;
  index: number;
  total: number;
  showAnswer: boolean;
  onReveal: () => void;
  onNext: () => void;
  onClose: () => void;
  onSend: (text: string) => void;
  he: boolean;
}) {
  const isLast = index >= total - 1;

  return (
    <div className="rounded-xl border-2 border-accent-gold/30 bg-accent-gold/5 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={16} className="text-accent-gold" />
          <span className="text-xs font-semibold text-accent-gold">
            {he ? "בוחן" : "Quiz"} {index + 1}/{total}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-[10px] text-text-tertiary hover:text-text-secondary"
        >
          {he ? "סגור" : "Close"}
        </button>
      </div>

      {/* Question */}
      <p className="text-sm text-foreground font-medium leading-relaxed">
        {question.question}
      </p>

      {/* Hint */}
      {question.hint && !showAnswer && (
        <p className="text-[10px] text-text-tertiary">
          {he ? "רמז: " : "Hint: "}{question.hint}
        </p>
      )}

      {/* Answer */}
      {showAnswer ? (
        <div className="bg-surface rounded-lg p-3 border border-border">
          <p className="text-sm text-text-secondary leading-relaxed">{question.answer}</p>
          <div className="flex gap-2 mt-3">
            {!isLast && (
              <button
                onClick={onNext}
                className="px-3 py-1.5 rounded text-xs bg-accent-gold/10 text-accent-gold hover:bg-accent-gold/20 transition-colors"
              >
                {he ? "הבא" : "Next"} &rarr;
              </button>
            )}
            <button
              onClick={() => onSend(question.question)}
              className="px-3 py-1.5 rounded text-xs bg-surface-sunken text-text-secondary hover:text-foreground transition-colors"
            >
              <span className="flex items-center gap-1">
                <MessageCircle size={10} />
                {he ? "שאל את קורצאק" : "Ask Korczak"}
              </span>
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={onReveal}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm
            bg-accent-gold text-background font-medium hover:bg-accent-gold/90 transition-colors"
        >
          <Eye size={14} />
          {he ? "גלה תשובה" : "Reveal Answer"}
        </button>
      )}
    </div>
  );
}
