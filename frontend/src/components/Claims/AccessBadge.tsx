"use client";

import type { ClaimPaper } from "@/lib/api";

const TONE_CLASSES: Record<string, string> = {
  positive: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  neutral: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  warning: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  muted: "bg-white/5 text-white/50 border-white/10",
};

interface Props {
  paper: Pick<ClaimPaper, "access_status" | "access_url" | "access_ui">;
  className?: string;
}

/**
 * Renders the open-access / paywall status of a paper as a compact badge.
 * When an access_url is present, the badge is an anchor that opens the
 * reading URL in a new tab.
 */
export function AccessBadge({ paper, className = "" }: Props) {
  const status = paper.access_status || "unknown";
  const ui = paper.access_ui || { label: status, tone: "muted", cta: null };
  const tone = TONE_CLASSES[ui.tone] || TONE_CLASSES.muted;
  const baseCls = `inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${tone} ${className}`;

  if (paper.access_url) {
    return (
      <a
        href={paper.access_url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${baseCls} hover:brightness-125 transition`}
        aria-label={ui.cta || ui.label}
      >
        <span>{ui.label}</span>
        <span aria-hidden="true">↗</span>
      </a>
    );
  }

  return <span className={baseCls}>{ui.label}</span>;
}
