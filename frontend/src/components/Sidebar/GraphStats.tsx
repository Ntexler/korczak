"use client";

import { useEffect, useState } from "react";
import { BookOpen, Brain, GitBranch, MessageSquare, Building2 } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { getGraphStats } from "@/lib/api";

const STAT_CONFIG = [
  { key: "total_papers", label: "Papers", icon: BookOpen, color: "text-accent-blue" },
  { key: "total_concepts", label: "Concepts", icon: Brain, color: "text-accent-gold" },
  { key: "total_relationships", label: "Relations", icon: GitBranch, color: "text-accent-green" },
  { key: "total_claims", label: "Claims", icon: MessageSquare, color: "text-accent-amber" },
  { key: "total_entities", label: "Entities", icon: Building2, color: "text-text-secondary" },
] as const;

export default function GraphStats() {
  const { graphStats, setGraphStats } = useChatStore();
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getGraphStats()
      .then((stats) => {
        setGraphStats(stats);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [setGraphStats]);

  if (!graphStats) return null;

  return (
    <div className="grid grid-cols-2 gap-2">
      {STAT_CONFIG.map((stat, i) => {
        const value = graphStats[stat.key as keyof typeof graphStats] ?? 0;
        return (
          <div
            key={stat.key}
            className={`flex items-center gap-2 p-2.5 rounded-lg bg-background/50 ${
              loaded ? "animate-count-up" : ""
            }`}
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <stat.icon size={14} className={stat.color} />
            <div>
              <p className="text-sm font-semibold text-foreground leading-none">
                {value.toLocaleString()}
              </p>
              <p className="text-[10px] text-text-secondary">{stat.label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
