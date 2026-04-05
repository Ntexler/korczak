"use client";

import { useEffect, useState, useCallback } from "react";
import { MessageCircle, ThumbsUp, ThumbsDown, Send, CheckCircle2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Discussion {
  id: string;
  title?: string;
  body: string;
  author_id: string;
  upvotes: number;
  downvotes: number;
  is_resolved: boolean;
  created_at: string;
  replies?: Discussion[];
}

interface DiscussionThreadProps {
  targetType: string;
  targetId: string;
  researcherId?: string;
}

export default function DiscussionThread({ targetType, targetId, researcherId }: DiscussionThreadProps) {
  const [discussions, setDiscussions] = useState<Discussion[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { locale } = useLocaleStore();

  const fetchDiscussions = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/social/discussions?target_type=${targetType}&target_id=${targetId}`
      );
      if (res.ok) {
        const data = await res.json();
        setDiscussions(data.discussions || []);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }, [targetType, targetId]);

  useEffect(() => {
    fetchDiscussions();
  }, [fetchDiscussions]);

  const handleSubmit = async (parentId?: string) => {
    if (!newBody.trim() || !researcherId || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/social/discussions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: targetType,
          target_id: targetId,
          author_id: researcherId,
          title: parentId ? undefined : newTitle.trim() || undefined,
          body: newBody.trim(),
          parent_id: parentId || undefined,
        }),
      });
      if (res.ok) {
        setNewTitle("");
        setNewBody("");
        setShowNew(false);
        setReplyTo(null);
        await fetchDiscussions();
      }
    } catch {
      // Silently fail
    } finally {
      setSubmitting(false);
    }
  };

  const handleVote = async (discussionId: string, vote: "up" | "down") => {
    if (!researcherId) return;
    try {
      await fetch(
        `${API_BASE}/social/discussions/${discussionId}/vote?voter_id=${researcherId}&vote=${vote}`,
        { method: "POST" }
      );
      await fetchDiscussions();
    } catch {
      // Silently fail
    }
  };

  const renderReplyForm = (parentId: string) => (
    <div className="ml-6 mt-2 space-y-1.5">
      <textarea
        value={newBody}
        onChange={(e) => setNewBody(e.target.value)}
        placeholder={locale === "he" ? "כתוב תגובה..." : "Write a reply..."}
        rows={2}
        className="w-full px-2 py-1.5 rounded bg-surface border border-border text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold resize-none"
      />
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleSubmit(parentId)}
          disabled={submitting || !newBody.trim()}
          className="flex items-center gap-1 px-2 py-1 rounded bg-accent-gold text-background text-[10px] font-medium disabled:opacity-50"
        >
          <Send size={9} />
          {locale === "he" ? "שלח" : "Reply"}
        </button>
        <button
          onClick={() => { setReplyTo(null); setNewBody(""); }}
          className="text-[10px] text-text-tertiary hover:text-text-secondary"
        >
          {locale === "he" ? "ביטול" : "Cancel"}
        </button>
      </div>
    </div>
  );

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[10px] uppercase tracking-wider font-semibold text-text-tertiary flex items-center gap-1.5">
          <MessageCircle size={11} />
          {locale === "he" ? "דיונים" : "Discussions"} ({discussions.length})
        </h3>
        {researcherId && (
          <button
            onClick={() => setShowNew(!showNew)}
            className="text-[10px] text-accent-gold hover:underline"
          >
            {showNew
              ? (locale === "he" ? "ביטול" : "Cancel")
              : (locale === "he" ? "התחל דיון" : "Start discussion")
            }
          </button>
        )}
      </div>

      {/* New discussion form */}
      {showNew && (
        <div className="space-y-2 p-3 rounded-lg bg-surface-sunken border border-border">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={locale === "he" ? "כותרת הדיון (אופציונלי)..." : "Discussion title (optional)..."}
            className="w-full px-2 py-1.5 rounded bg-surface border border-border text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold"
          />
          <textarea
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            placeholder={locale === "he" ? "מה דעתך?" : "What's your take?"}
            rows={3}
            className="w-full px-2 py-1.5 rounded bg-surface border border-border text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold resize-none"
          />
          <div className="flex justify-end">
            <button
              onClick={() => handleSubmit()}
              disabled={submitting || !newBody.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-accent-gold text-background text-xs font-medium hover:bg-accent-gold/90 disabled:opacity-50"
            >
              <Send size={10} />
              {locale === "he" ? "פרסם" : "Post"}
            </button>
          </div>
        </div>
      )}

      {/* Discussions list */}
      {loading ? (
        <div className="text-xs text-text-tertiary py-2">
          {locale === "he" ? "טוען..." : "Loading..."}
        </div>
      ) : discussions.length === 0 ? (
        <div className="text-xs text-text-tertiary py-2">
          {locale === "he" ? "אין דיונים עדיין." : "No discussions yet."}
        </div>
      ) : (
        <div className="space-y-3">
          {discussions.map((d) => (
            <div key={d.id} className="space-y-1">
              <div className="p-2.5 rounded-lg bg-surface-sunken border border-border/50">
                <div className="flex items-start gap-2">
                  <div className="flex flex-col items-center gap-0.5 pt-0.5">
                    <button
                      onClick={() => handleVote(d.id, "up")}
                      className="p-0.5 rounded hover:bg-accent-green/10 text-text-tertiary hover:text-accent-green"
                    >
                      <ThumbsUp size={10} />
                    </button>
                    <span className="text-[10px] text-text-tertiary">{d.upvotes - d.downvotes}</span>
                    <button
                      onClick={() => handleVote(d.id, "down")}
                      className="p-0.5 rounded hover:bg-accent-red/10 text-text-tertiary hover:text-accent-red"
                    >
                      <ThumbsDown size={10} />
                    </button>
                  </div>
                  <div className="flex-1 min-w-0">
                    {d.title && (
                      <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                        {d.title}
                        {d.is_resolved && <CheckCircle2 size={10} className="text-accent-green" />}
                      </h4>
                    )}
                    <p className="text-xs text-text-secondary leading-relaxed mt-0.5">{d.body}</p>
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className="text-[10px] text-text-tertiary">
                        {new Date(d.created_at).toLocaleDateString()}
                      </span>
                      {researcherId && (
                        <button
                          onClick={() => setReplyTo(replyTo === d.id ? null : d.id)}
                          className="text-[10px] text-accent-gold hover:underline"
                        >
                          {locale === "he" ? "השב" : "Reply"}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Replies */}
              {d.replies && d.replies.length > 0 && (
                <div className="ml-6 space-y-1">
                  {d.replies.map((reply) => (
                    <div key={reply.id} className="p-2 rounded bg-surface-sunken/50 border-l-2 border-accent-gold/20">
                      <p className="text-xs text-text-secondary leading-relaxed">{reply.body}</p>
                      <span className="text-[10px] text-text-tertiary mt-1 block">
                        {new Date(reply.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Reply form */}
              {replyTo === d.id && renderReplyForm(d.id)}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
