"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { MessageCircle, Send, Loader2, Reply } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getComments, createComment } from "@/lib/api";
import VoteButton from "./VoteButton";

interface PaperCommentsProps {
  paperId: string;
  userId?: string;
}

interface Comment {
  id: string;
  content: string;
  user_id: string;
  upvotes: number;
  downvotes: number;
  created_at: string;
  replies: Comment[];
}

export default function PaperComments({ paperId, userId }: PaperCommentsProps) {
  const { t } = useLocaleStore();
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadComments();
  }, [paperId]);

  const loadComments = async () => {
    setLoading(true);
    try {
      const res = await getComments(paperId);
      setComments(res.comments || []);
    } catch {
      // Handle
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (parentId?: string) => {
    if (!userId || !newComment.trim()) return;
    setSubmitting(true);
    try {
      await createComment(paperId, userId, newComment.trim(), parentId);
      setNewComment("");
      setReplyingTo(null);
      loadComments();
    } catch {
      // Handle
    } finally {
      setSubmitting(false);
    }
  };

  const renderComment = (comment: Comment, depth: number = 0) => (
    <div key={comment.id} className={`${depth > 0 ? "ml-6 border-l border-border-subtle pl-3" : ""}`}>
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-2"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <p className="text-xs text-foreground leading-relaxed">{comment.content}</p>
            <div className="flex items-center gap-3 mt-1.5">
              <span className="text-[9px] text-text-tertiary">
                {new Date(comment.created_at).toLocaleDateString()}
              </span>
              <VoteButton
                targetType="comment"
                targetId={comment.id}
                userId={userId}
                upvotes={comment.upvotes}
                downvotes={comment.downvotes}
                size={10}
              />
              {userId && (
                <button
                  onClick={() => setReplyingTo(comment.id)}
                  className="flex items-center gap-0.5 text-[10px] text-text-tertiary hover:text-accent-gold"
                >
                  <Reply size={10} />
                  {t.reply}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Reply input */}
        {replyingTo === comment.id && (
          <div className="flex gap-1.5 mt-2">
            <input
              type="text"
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit(comment.id)}
              placeholder={t.addComment}
              className="flex-1 bg-surface-sunken border border-border-subtle rounded-lg px-2.5 py-1.5
                text-xs text-foreground placeholder:text-text-tertiary focus:outline-none"
              autoFocus
            />
            <button
              onClick={() => handleSubmit(comment.id)}
              disabled={!newComment.trim() || submitting}
              className="p-1.5 rounded-lg bg-accent-gold/20 text-accent-gold disabled:opacity-40"
            >
              <Send size={12} />
            </button>
          </div>
        )}
      </motion.div>

      {/* Nested replies */}
      {comment.replies?.map((reply) => renderComment(reply, depth + 1))}
    </div>
  );

  return (
    <div className="py-3">
      <div className="flex items-center gap-2 mb-3">
        <MessageCircle size={14} className="text-accent-gold" />
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {t.comments}
        </h3>
      </div>

      {loading ? (
        <div className="flex justify-center py-3">
          <Loader2 size={14} className="animate-spin text-text-tertiary" />
        </div>
      ) : (
        <>
          {comments.length === 0 && (
            <p className="text-xs text-text-tertiary text-center py-3">{t.noComments}</p>
          )}
          <div className="space-y-1">
            {comments.map((c) => renderComment(c))}
          </div>
        </>
      )}

      {/* New comment input */}
      {userId && !replyingTo && (
        <div className="flex gap-1.5 mt-3">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder={t.addComment}
            className="flex-1 bg-surface-sunken border border-border-subtle rounded-lg px-2.5 py-1.5
              text-xs text-foreground placeholder:text-text-tertiary focus:outline-none"
          />
          <button
            onClick={() => handleSubmit()}
            disabled={!newComment.trim() || submitting}
            className="p-1.5 rounded-lg bg-accent-gold/20 text-accent-gold disabled:opacity-40"
          >
            {submitting ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          </button>
        </div>
      )}
    </div>
  );
}
