"use client";

import { Clock } from "lucide-react";

interface ReadingTimerProps {
  seconds: number;
}

export default function ReadingTimer({ seconds }: ReadingTimerProps) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const display = mins > 0 ? `${mins}m ${secs.toString().padStart(2, "0")}s` : `${secs}s`;

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-surface-sunken text-text-secondary">
      <Clock size={12} className="text-accent-gold/60" />
      <span className="text-[11px] font-mono tabular-nums">{display}</span>
    </div>
  );
}
