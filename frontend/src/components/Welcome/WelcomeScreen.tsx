"use client";

import { motion } from "framer-motion";
import { Compass, BookOpen, Brain, Sparkles } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

const SUGGESTED_PROMPTS = [
  {
    icon: Brain,
    text: "What are the main debates in anthropology?",
    color: "text-accent-gold",
    featured: true,
  },
  {
    icon: BookOpen,
    text: "How does participant observation work?",
    color: "text-accent-blue",
  },
  {
    icon: Sparkles,
    text: "What connects sleep research to cognitive anthropology?",
    color: "text-accent-green",
  },
  {
    icon: Compass,
    text: "Show me the most influential papers on decolonization",
    color: "text-accent-amber",
  },
];

interface WelcomeScreenProps {
  onSend: (message: string) => void;
}

export default function WelcomeScreen({ onSend }: WelcomeScreenProps) {
  const graphStats = useChatStore((s) => s.graphStats);

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 welcome-bg">
      {/* Title */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center mb-10"
      >
        <div className="flex items-center justify-center gap-3 mb-5">
          <div className="w-14 h-14 rounded-full bg-accent-gold-dim flex items-center justify-center animate-glow-pulse">
            <Compass size={28} className="text-accent-gold" />
          </div>
        </div>
        <h1
          className="text-4xl sm:text-5xl font-bold tracking-tight mb-3"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          Welcome to <span className="text-accent-gold">Korczak</span>
        </h1>
        <p className="text-text-secondary text-lg italic">
          See what you don&apos;t see
        </p>

        {/* Graph stats */}
        {graphStats && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="flex items-center justify-center gap-6 text-sm mt-6"
          >
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {graphStats.total_papers.toLocaleString()}
              </span>
              <span className="text-text-tertiary text-xs">papers</span>
            </div>
            <div className="w-px h-8 bg-border" />
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {graphStats.total_concepts.toLocaleString()}
              </span>
              <span className="text-text-tertiary text-xs">concepts</span>
            </div>
            <div className="w-px h-8 bg-border" />
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {graphStats.total_relationships.toLocaleString()}
              </span>
              <span className="text-text-tertiary text-xs">connections</span>
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* Suggested prompts */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.5 }}
        className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full"
      >
        {SUGGESTED_PROMPTS.map((prompt, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 + i * 0.1 }}
            onClick={() => onSend(prompt.text)}
            className={`flex items-start gap-3 rounded-xl border text-left transition-all duration-200 group
              ${
                prompt.featured
                  ? "sm:col-span-2 p-5 bg-gradient-to-r from-accent-gold/[0.04] to-surface border-accent-gold/20 hover:border-accent-gold/40"
                  : "p-4 bg-surface border-border hover:border-accent-gold/30 hover:bg-surface-hover"
              }`}
          >
            <prompt.icon
              size={prompt.featured ? 22 : 18}
              className={`${prompt.color} mt-0.5 flex-shrink-0 group-hover:scale-110 transition-transform`}
            />
            <span
              className={`text-text-secondary group-hover:text-foreground transition-colors ${
                prompt.featured ? "text-base" : "text-sm"
              }`}
            >
              {prompt.text}
            </span>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
