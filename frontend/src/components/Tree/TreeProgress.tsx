"use client";

import { TreePine } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface TreeProgressProps {
  stats: {
    total_nodes: number;
    completed: number;
    available: number;
    branch_points: number;
    max_depth: number;
    trunk_nodes: number;
  };
}

export default function TreeProgress({ stats }: TreeProgressProps) {
  const { t } = useLocaleStore();
  const pct = stats.total_nodes > 0
    ? Math.round((stats.completed / stats.total_nodes) * 100)
    : 0;

  return (
    <div className="flex items-center gap-3 px-3 py-1 rounded-lg bg-surface-sunken">
      <div className="flex items-center gap-1.5">
        <div className="w-12 h-1.5 bg-border rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-gold rounded-full transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-[10px] text-text-tertiary font-mono">{pct}%</span>
      </div>
      <div className="h-3 w-px bg-border" />
      <span className="text-[10px] text-text-tertiary">
        {stats.completed}/{stats.total_nodes} {t.concepts}
      </span>
      <span className="text-[10px] text-text-tertiary">
        {t.depthReached}: {stats.max_depth}
      </span>
    </div>
  );
}
