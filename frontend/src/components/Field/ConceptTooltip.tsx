"use client";

import { useCallback, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface ConceptTooltipProps {
  conceptId: string;
  name: string;
  onSelect: (id: string) => void;
}

export default function ConceptTooltip({
  conceptId,
  name,
  onSelect,
}: ConceptTooltipProps) {
  const [tooltip, setTooltip] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);
  const fetchedRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = useCallback(() => {
    timeoutRef.current = setTimeout(async () => {
      setVisible(true);
      if (!fetchedRef.current) {
        fetchedRef.current = true;
        try {
          const res = await fetch(
            `${API_BASE}/graph/concepts/${encodeURIComponent(conceptId)}`
          );
          if (res.ok) {
            const data = await res.json();
            const def =
              data.definition ||
              data.description ||
              data.summary ||
              "No definition available";
            setTooltip(
              typeof def === "string" ? def.slice(0, 120) : String(def)
            );
          } else {
            setTooltip("No definition available");
          }
        } catch {
          setTooltip("No definition available");
        }
      }
    }, 300);
  }, [conceptId]);

  const handleMouseLeave = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setVisible(false);
  }, []);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => onSelect(conceptId)}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className="text-accent-gold underline decoration-accent-gold/40 underline-offset-2
                   hover:decoration-accent-gold cursor-pointer transition-colors
                   bg-transparent border-none p-0 font-inherit text-inherit"
        style={{ fontSize: "inherit", lineHeight: "inherit" }}
      >
        {name}
      </button>
      {visible && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                     px-3 py-2 rounded-lg bg-surface-elevated border border-border
                     text-xs text-text-secondary whitespace-normal max-w-[240px]
                     shadow-lg pointer-events-none"
        >
          {tooltip ?? "Loading..."}
        </span>
      )}
    </span>
  );
}
