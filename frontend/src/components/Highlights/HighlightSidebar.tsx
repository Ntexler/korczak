"use client";

import { useEffect } from "react";
import { Highlighter, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useHighlightStore } from "@/stores/highlightStore";
import { getHighlights } from "@/lib/api";

interface HighlightSidebarProps {
  userId: string;
}

export default function HighlightSidebar({ userId }: HighlightSidebarProps) {
  const { t } = useLocaleStore();
  const { highlights, isLoading, setHighlights, setLoading } = useHighlightStore();

  useEffect(() => {
    loadHighlights();
  }, [userId]);

  const loadHighlights = async () => {
    setLoading(true);
    try {
      const res = await getHighlights(userId);
      setHighlights(res.highlights || []);
    } catch {
      // Handle silently
    } finally {
      setLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="py-3">
        <div className="flex items-center gap-2 mb-3">
          <Highlighter size={14} className="text-accent-gold" />
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            {t.recentHighlights}
          </h3>
        </div>
        <div className="flex justify-center py-3">
          <Loader2 size={14} className="animate-spin text-text-tertiary" />
        </div>
      </div>
    );
  }

  if (highlights.length === 0) return null;

  return (
    <div className="py-3">
      <div className="flex items-center gap-2 mb-3">
        <Highlighter size={14} className="text-accent-gold" />
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {t.recentHighlights}
        </h3>
      </div>
      <div className="space-y-1.5">
        {highlights.slice(0, 5).map((h) => (
          <div
            key={h.id}
            className="px-2.5 py-2 rounded-lg bg-surface-sunken border-l-2 transition-colors hover:bg-surface-hover"
            style={{ borderLeftColor: h.color }}
          >
            <p className="text-[11px] text-foreground line-clamp-2 leading-relaxed">
              &ldquo;{h.highlighted_text}&rdquo;
            </p>
            {h.annotation && (
              <p className="text-[10px] text-text-tertiary mt-1 italic">{h.annotation}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
