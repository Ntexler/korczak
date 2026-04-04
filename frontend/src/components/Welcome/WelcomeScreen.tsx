"use client";

import { motion } from "framer-motion";
import { Compass, BookOpen, Brain, Sparkles } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";


const ICONS = [Brain, BookOpen, Sparkles, Compass];
const COLORS = ["text-accent-gold", "text-accent-blue", "text-accent-green", "text-accent-amber"];

interface WelcomeScreenProps {
  onSend: (message: string) => void;
}

export default function WelcomeScreen({ onSend }: WelcomeScreenProps) {
  const graphStats = useChatStore((s) => s.graphStats);
  const { t, fonts: f } = useLocaleStore();
  const prompts = t.prompts as unknown as string[];
  const statsLabel = t.statsLabel as unknown as { papers: string; concepts: string; connections: string };

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
          style={{ fontFamily: f.serif }}
        >
          {t.welcomeTitle}{" "}
          <span className="text-accent-gold">{t.appName}</span>
        </h1>
        <p className="text-text-secondary text-lg italic">
          {t.tagline}
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
              <span className="text-text-tertiary text-xs">{statsLabel.papers}</span>
            </div>
            <div className="w-px h-8 bg-border" />
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {graphStats.total_concepts.toLocaleString()}
              </span>
              <span className="text-text-tertiary text-xs">{statsLabel.concepts}</span>
            </div>
            <div className="w-px h-8 bg-border" />
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {graphStats.total_relationships.toLocaleString()}
              </span>
              <span className="text-text-tertiary text-xs">{statsLabel.connections}</span>
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
        {prompts.map((text, i) => {
          const Icon = ICONS[i] || Compass;
          const color = COLORS[i] || "text-accent-gold";
          const featured = i === 0;
          return (
            <motion.button
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 + i * 0.1 }}
              onClick={() => onSend(text)}
              className={`flex items-start gap-3 rounded-xl border text-left transition-all duration-200 group
                ${
                  featured
                    ? "sm:col-span-2 p-5 bg-gradient-to-r from-accent-gold/[0.04] to-surface border-accent-gold/20 hover:border-accent-gold/40"
                    : "p-4 bg-surface border-border hover:border-accent-gold/30 hover:bg-surface-hover"
                }`}
            >
              <Icon
                size={featured ? 22 : 18}
                className={`${color} mt-0.5 flex-shrink-0 group-hover:scale-110 transition-transform`}
              />
              <span
                className={`text-text-secondary group-hover:text-foreground transition-colors ${
                  featured ? "text-base" : "text-sm"
                }`}
              >
                {text}
              </span>
            </motion.button>
          );
        })}
      </motion.div>
    </div>
  );
}
