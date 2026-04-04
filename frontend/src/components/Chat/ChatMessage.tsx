"use client";

import { motion } from "framer-motion";
import { Compass, Sparkles, User } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  conceptsReferenced?: { id: string; name: string }[];
  insight?: { type: string; content: string } | null;
  onSend?: (message: string) => void;
}

const FOLLOW_UPS = [
  "Tell me more",
  "What's controversial?",
  "Show related concepts",
];

export default function ChatMessage({
  role,
  content,
  conceptsReferenced,
  insight,
  onSend,
}: ChatMessageProps) {
  const isUser = role === "user";
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-5`}
    >
      <div className={`flex gap-3 max-w-[85%] ${isUser ? "flex-row-reverse" : ""}`}>
        {/* Avatar */}
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-1 ${
            isUser
              ? "bg-accent-blue/15 text-accent-blue"
              : "bg-accent-gold-dim text-accent-gold"
          }`}
        >
          {isUser ? <User size={16} /> : <Compass size={16} />}
        </div>

        {/* Message body */}
        <div className="flex flex-col gap-2">
          <div
            className={`px-4 py-3 rounded-2xl ${
              isUser
                ? "bg-user-bubble border border-border-subtle text-foreground rounded-br-sm"
                : "bg-surface border border-border-subtle text-foreground rounded-bl-sm"
            }`}
          >
            <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm" style={{ lineHeight: '1.75' }}>
              {renderContent(content)}
            </div>
          </div>

          {/* Concept badges — staggered entrance */}
          {!isUser && conceptsReferenced && conceptsReferenced.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-1">
              {conceptsReferenced.map((c, i) => (
                <motion.button
                  key={c.id}
                  initial={{ opacity: 0, scale: 0.8, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ delay: i * 0.05, duration: 0.2 }}
                  onClick={() => setSelectedConceptId(c.id)}
                  className="concept-badge"
                >
                  {c.name}
                </motion.button>
              ))}
            </div>
          )}

          {/* Insight callout */}
          {!isUser && insight && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2, duration: 0.3 }}
              className="insight-callout"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Sparkles size={14} className="text-accent-gold" />
                <span className="text-xs font-semibold text-accent-gold uppercase tracking-wide">
                  {insight.type === "blind_spot"
                    ? "Blind Spot"
                    : insight.type === "connection"
                      ? "Connection"
                      : "Insight"}
                </span>
              </div>
              <p className="text-sm text-text-secondary leading-relaxed">
                {insight.content}
              </p>
            </motion.div>
          )}

          {/* Follow-up suggestion chips */}
          {!isUser && onSend && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4, duration: 0.3 }}
              className="flex flex-wrap gap-1.5 px-1"
            >
              {FOLLOW_UPS.map((chip) => (
                <button
                  key={chip}
                  onClick={() => onSend(chip)}
                  className="follow-up-chip"
                >
                  {chip}
                </button>
              ))}
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function renderContent(content: string) {
  const lines = content.split("\n");
  return lines.map((line, i) => {
    let processed: React.ReactNode = line;
    if (typeof processed === "string") {
      const parts = processed.split(/\*\*(.+?)\*\*/g);
      if (parts.length > 1) {
        processed = parts.map((part, j) =>
          j % 2 === 1 ? (
            <strong key={j} className="text-foreground font-semibold">
              {part}
            </strong>
          ) : (
            part
          )
        );
      }
    }
    return (
      <span key={i}>
        {processed}
        {i < lines.length - 1 && "\n"}
      </span>
    );
  });
}
