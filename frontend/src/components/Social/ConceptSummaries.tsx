"use client";

import { useEffect, useState, useCallback } from "react";
import { PenLine, ThumbsUp, ThumbsDown, History, Send, ChevronDown, ChevronUp } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Summary {
  id: string;
  title: string;
  body: string;
  author_id: string;
  upvotes: number;
  downvotes: number;
  version: number;
  created_at: string;
  updated_at: string;
  researcher_profiles?: { display_name: string; institution?: string };
}

interface ConceptSummariesProps {
  conceptId: string;
  researcherId?: string;
}

export default function ConceptSummaries({ conceptId, researcherId }: ConceptSummariesProps) {
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWrite, setShowWrite] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const { locale } = useLocaleStore();

  const fetchSummaries = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/social/concepts/${conceptId}/summaries?sort=top`);
      if (res.ok) {
        const data = await res.json();
        setSummaries(data.summaries || []);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }, [conceptId]);

  useEffect(() => {
    fetchSummaries();
  }, [fetchSummaries]);

  const handleSubmit = async () => {
    if (!title.trim() || !body.trim() || !researcherId || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/social/summaries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept_id: conceptId,
          author_id: researcherId,
          title: title.trim(),
          body: body.trim(),
        }),
      });
      if (res.ok) {
        setTitle("");
        setBody("");
        setShowWrite(false);
        await fetchSummaries();
      }
    } catch {
      // Silently fail
    } finally {
      setSubmitting(false);
    }
  };

  const handleVote = async (summaryId: string, vote: "up" | "down") => {
    if (!researcherId) return;
    try {
      await fetch(`${API_BASE}/social/summaries/${summaryId}/vote?voter_id=${researcherId}&vote=${vote}`, {
        method: "POST",
      });
      await fetchSummaries();
    } catch {
      // Silently fail
    }
  };

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[10px] uppercase tracking-wider font-semibold text-text-tertiary flex items-center gap-1.5">
          <PenLine size={11} />
          {locale === "he" ? "סיכומים קהילתיים" : "Community Summaries"} ({summaries.length})
        </h3>
        {researcherId && (
          <button
            onClick={() => setShowWrite(!showWrite)}
            className="text-[10px] text-accent-gold hover:underline"
          >
            {showWrite
              ? (locale === "he" ? "ביטול" : "Cancel")
              : (locale === "he" ? "כתוב סיכום" : "Write summary")
            }
          </button>
        )}
      </div>

      {/* Write form */}
      {showWrite && (
        <div className="space-y-2 p-3 rounded-lg bg-surface-sunken border border-border">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={locale === "he" ? "כותרת הסיכום..." : "Summary title..."}
            className="w-full px-2 py-1.5 rounded bg-surface border border-border text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={locale === "he" ? "כתוב את הפרשנות שלך..." : "Write your interpretation..."}
            rows={4}
            className="w-full px-2 py-1.5 rounded bg-surface border border-border text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold resize-none"
          />
          <div className="flex justify-end">
            <button
              onClick={handleSubmit}
              disabled={submitting || !title.trim() || !body.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-accent-gold text-background text-xs font-medium hover:bg-accent-gold/90 disabled:opacity-50"
            >
              <Send size={10} />
              {locale === "he" ? "פרסם" : "Publish"}
            </button>
          </div>
        </div>
      )}

      {/* Summaries list */}
      {loading ? (
        <div className="text-xs text-text-tertiary py-2">
          {locale === "he" ? "טוען..." : "Loading..."}
        </div>
      ) : summaries.length === 0 ? (
        <div className="text-xs text-text-tertiary py-2">
          {locale === "he" ? "אין עדיין סיכומים. היה הראשון!" : "No summaries yet. Be the first!"}
        </div>
      ) : (
        <div className="space-y-2">
          {summaries.map((s) => (
            <div key={s.id} className="p-3 rounded-lg bg-surface-sunken border border-border/50">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <button
                    onClick={() => toggleExpand(s.id)}
                    className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-accent-gold transition-colors text-left"
                  >
                    {expanded.has(s.id) ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    {s.title}
                  </button>
                  <div className="flex items-center gap-2 mt-0.5 text-[10px] text-text-tertiary">
                    <span>{s.researcher_profiles?.display_name || "Anonymous"}</span>
                    {s.researcher_profiles?.institution && (
                      <span>@ {s.researcher_profiles.institution}</span>
                    )}
                    {s.version > 1 && (
                      <span className="flex items-center gap-0.5">
                        <History size={8} /> v{s.version}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => handleVote(s.id, "up")}
                    className="p-0.5 rounded hover:bg-accent-green/10 text-text-tertiary hover:text-accent-green"
                  >
                    <ThumbsUp size={10} />
                  </button>
                  <span className="text-[10px] text-text-tertiary min-w-[20px] text-center">
                    {s.upvotes - s.downvotes}
                  </span>
                  <button
                    onClick={() => handleVote(s.id, "down")}
                    className="p-0.5 rounded hover:bg-accent-red/10 text-text-tertiary hover:text-accent-red"
                  >
                    <ThumbsDown size={10} />
                  </button>
                </div>
              </div>
              {expanded.has(s.id) && (
                <div className="mt-2 text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
                  {s.body}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
