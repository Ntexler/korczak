"use client";

import { useState, useEffect } from "react";
import { Highlighter, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getPublicHighlights } from "@/lib/api";

interface SharedHighlightsProps {
  sourceType: string;
  sourceId: string;
}

export default function SharedHighlights({ sourceType, sourceId }: SharedHighlightsProps) {
  const { t } = useLocaleStore();
  const [highlights, setHighlights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHighlights();
  }, [sourceType, sourceId]);

  const loadHighlights = async () => {
    setLoading(true);
    try {
      const res = await getPublicHighlights(sourceType, sourceId);
      setHighlights(res.highlights || []);
    } catch {
      // Handle
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-3">
        <Loader2 size={14} className="animate-spin text-text-tertiary" />
      </div>
    );
  }

  if (highlights.length === 0) return null;

  return (
    <div className="py-3">
      <div className="flex items-center gap-2 mb-2">
        <Highlighter size={12} className="text-accent-gold/60" />
        <h4 className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider">
          {t.sharedHighlights} ({highlights.length})
        </h4>
      </div>
      <div className="space-y-1.5">
        {highlights.slice(0, 5).map((h) => (
          <div
            key={h.id}
            className="px-2.5 py-1.5 rounded-lg bg-surface-sunken border-l-2"
            style={{ borderLeftColor: h.color }}
          >
            <p className="text-[11px] text-foreground line-clamp-2">
              &ldquo;{h.highlighted_text}&rdquo;
            </p>
            {h.annotation && (
              <p className="text-[10px] text-text-tertiary mt-0.5 italic">{h.annotation}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
