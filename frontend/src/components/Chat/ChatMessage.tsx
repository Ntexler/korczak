"use client";

import { motion } from "framer-motion";
import { Compass, Sparkles, User } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  conceptsReferenced?: { id: string; name: string }[];
  insight?: { type: string; content: string } | null;
  onSend?: (message: string) => void;
}

export default function ChatMessage({
  role,
  content,
  conceptsReferenced,
  insight,
  onSend,
}: ChatMessageProps) {
  const isUser = role === "user";
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const { t } = useLocaleStore();

  const followUps = [t.tellMeMore, t.whatsControversial, t.showRelated];

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
                    ? t.blindSpot
                    : insight.type === "connection"
                      ? t.connection
                      : t.insight}
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
              {followUps.map((chip) => (
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
    const trimmed = line.trim();

    // Headers
    if (trimmed.startsWith("### ")) {
      return <h4 key={i} className="text-sm font-bold text-foreground mt-3 mb-1">{renderInline(trimmed.slice(4))}</h4>;
    }
    if (trimmed.startsWith("## ")) {
      return <h3 key={i} className="text-sm font-bold text-foreground mt-4 mb-1">{renderInline(trimmed.slice(3))}</h3>;
    }
    if (trimmed.startsWith("# ")) {
      return <h2 key={i} className="text-base font-bold text-foreground mt-4 mb-1">{renderInline(trimmed.slice(2))}</h2>;
    }

    // Bullet lists
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      return (
        <div key={i} className="flex gap-2 ml-1 my-0.5">
          <span className="text-accent-gold mt-0.5 shrink-0">•</span>
          <span>{renderInline(trimmed.slice(2))}</span>
        </div>
      );
    }

    // Numbered lists
    const numMatch = trimmed.match(/^(\d+)\.\s(.+)/);
    if (numMatch) {
      return (
        <div key={i} className="flex gap-2 ml-1 my-0.5">
          <span className="text-text-tertiary shrink-0 w-4 text-right">{numMatch[1]}.</span>
          <span>{renderInline(numMatch[2])}</span>
        </div>
      );
    }

    // Blockquotes
    if (trimmed.startsWith("> ")) {
      return (
        <div key={i} className="border-l-2 border-accent-gold/40 pl-3 my-1 text-text-secondary italic">
          {renderInline(trimmed.slice(2))}
        </div>
      );
    }

    // Horizontal rule
    if (trimmed === "---" || trimmed === "***") {
      return <hr key={i} className="border-border my-2" />;
    }

    // Empty line
    if (!trimmed) {
      return <div key={i} className="h-2" />;
    }

    // Regular line with inline formatting
    return (
      <span key={i}>
        {renderInline(line)}
        {i < lines.length - 1 && "\n"}
      </span>
    );
  });
}

function renderInline(text: string): React.ReactNode {
  // Process inline markdown: **bold**, *italic*, `code`, [source_id]
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\])/g);
  return parts.map((part, j) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={j} className="text-foreground font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && !part.startsWith("**")) {
      return <em key={j} className="italic">{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={j} className="px-1 py-0.5 rounded bg-surface-sunken text-accent-gold text-[11px] font-mono">{part.slice(1, -1)}</code>;
    }
    // Source citations [source_id]
    if (part.startsWith("[") && part.endsWith("]") && part.length < 40) {
      return <span key={j} className="text-[10px] text-accent-blue align-super">{part}</span>;
    }
    return part;
  });
}
