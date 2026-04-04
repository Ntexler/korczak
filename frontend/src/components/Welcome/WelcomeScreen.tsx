"use client";

import { motion } from "framer-motion";
import { Compass, BookOpen, Brain, Sparkles } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

const SUGGESTED_PROMPTS = [
  {
    icon: Brain,
    text: "What are the main debates in anthropology?",
    color: "text-accent-gold",
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
    <div className="flex flex-col items-center justify-center h-full px-6">
      {/* Title */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center mb-10"
      >
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-accent-gold-dim flex items-center justify-center animate-glow-pulse">
            <Compass size={24} className="text-accent-gold" />
          </div>
        </div>
        <h1
          className="text-4xl font-bold tracking-tight mb-2"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          Welcome to <span className="text-accent-gold">Korczak</span>
        </h1>
        <p className="text-text-secondary text-lg">
          See what you don&apos;t see
        </p>

        {/* Graph stats */}
        {graphStats && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="text-text-secondary text-sm mt-4"
          >
            Your knowledge universe:{" "}
            <span className="text-foreground font-medium">
              {graphStats.total_papers.toLocaleString()}
            </span>{" "}
            papers,{" "}
            <span className="text-foreground font-medium">
              {graphStats.total_concepts.toLocaleString()}
            </span>{" "}
            concepts
          </motion.p>
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
            className="flex items-start gap-3 p-4 rounded-xl bg-surface border border-border
              hover:border-accent-gold/30 hover:bg-surface-hover
              text-left transition-all duration-200 group"
          >
            <prompt.icon
              size={18}
              className={`${prompt.color} mt-0.5 flex-shrink-0 group-hover:scale-110 transition-transform`}
            />
            <span className="text-sm text-text-secondary group-hover:text-foreground transition-colors">
              {prompt.text}
            </span>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
