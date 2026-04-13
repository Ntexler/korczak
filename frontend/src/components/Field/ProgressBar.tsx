"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface ProgressBarProps {
  field: string;
  userId: string;
}

interface ProgressData {
  field: string;
  completion_pct: number;
  current_position: string;
}

export default function ProgressBar({ field, userId }: ProgressBarProps) {
  const [progress, setProgress] = useState<ProgressData | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/features/fields/${encodeURIComponent(field)}/progress?user_id=${encodeURIComponent(userId)}`
        );
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setProgress(data);
        }
      } catch {
        // silently fail — progress bar is non-critical
      }
    })();
    return () => { cancelled = true; };
  }, [field, userId]);

  const pct = progress?.completion_pct ?? 0;

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 bg-surface-sunken border-t border-border">
      <span className="text-xs text-text-tertiary truncate max-w-[160px]">
        {field}
      </span>
      <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full bg-accent-gold transition-all duration-700"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-text-tertiary tabular-nums w-10 text-right">
        {Math.round(pct)}%
      </span>
      {progress?.current_position && (
        <span className="text-xs text-text-secondary truncate max-w-[140px] hidden sm:inline">
          {progress.current_position}
        </span>
      )}
    </div>
  );
}
