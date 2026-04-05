"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown, MessageSquare, Send } from "lucide-react";
import { submitConnectionFeedback } from "@/lib/api";
import { useLocaleStore } from "@/stores/localeStore";

interface ConnectionFeedbackProps {
  relationshipId: string;
  userId?: string;
  onFeedbackSent?: () => void;
}

export default function ConnectionFeedback({ relationshipId, userId, onFeedbackSent }: ConnectionFeedbackProps) {
  const [sent, setSent] = useState<string | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const { locale } = useLocaleStore();

  const handleFeedback = async (type: "agree" | "disagree") => {
    if (loading || sent) return;
    setLoading(true);
    try {
      await submitConnectionFeedback(relationshipId, type, comment || undefined, userId);
      setSent(type);
      setShowComment(false);
      onFeedbackSent?.();
    } catch {
      // Silently fail — non-critical action
    } finally {
      setLoading(false);
    }
  };

  const handleCommentSubmit = async () => {
    if (!comment.trim() || loading) return;
    setLoading(true);
    try {
      await submitConnectionFeedback(relationshipId, "disagree", comment, userId);
      setSent("disagree");
      setShowComment(false);
      onFeedbackSent?.();
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-accent-gold/70">
        {sent === "agree" ? <ThumbsUp size={10} /> : <ThumbsDown size={10} />}
        <span>{locale === "he" ? "תודה על המשוב" : "Thanks for your feedback"}</span>
      </div>
    );
  }

  return (
    <div className="mt-1" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center gap-1">
        <button
          onClick={(e) => { e.stopPropagation(); handleFeedback("agree"); }}
          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] text-text-tertiary hover:text-accent-green hover:bg-accent-green/10 transition-colors"
          title={locale === "he" ? "מסכים עם החיבור" : "Agree with this connection"}
        >
          <ThumbsUp size={9} />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); handleFeedback("disagree"); }}
          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] text-text-tertiary hover:text-accent-red hover:bg-accent-red/10 transition-colors"
          title={locale === "he" ? "לא מסכים" : "Disagree"}
        >
          <ThumbsDown size={9} />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); setShowComment(!showComment); }}
          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] text-text-tertiary hover:text-accent-gold hover:bg-accent-gold/10 transition-colors"
          title={locale === "he" ? "הוסף הערה" : "Add comment"}
        >
          <MessageSquare size={9} />
        </button>
      </div>
      {showComment && (
        <div className="flex items-center gap-1 mt-1">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCommentSubmit()}
            placeholder={locale === "he" ? "למה לא נכון?" : "Why is this wrong?"}
            className="flex-1 px-2 py-1 rounded bg-surface-sunken border border-border text-[10px] text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={(e) => { e.stopPropagation(); handleCommentSubmit(); }}
            className="p-1 rounded hover:bg-surface-hover text-text-tertiary hover:text-accent-gold"
          >
            <Send size={10} />
          </button>
        </div>
      )}
    </div>
  );
}
