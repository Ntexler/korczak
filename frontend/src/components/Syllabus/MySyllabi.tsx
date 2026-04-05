"use client";

import { useState, useEffect } from "react";
import { BookOpenCheck, Loader2, ChevronRight } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getUserSyllabi } from "@/lib/api";

interface MySyllabiProps {
  userId: string;
  onSelect?: (syllabusId: string) => void;
}

export default function MySyllabi({ userId, onSelect }: MySyllabiProps) {
  const { t } = useLocaleStore();
  const [syllabi, setSyllabi] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSyllabi();
  }, [userId]);

  const loadSyllabi = async () => {
    setLoading(true);
    try {
      const res = await getUserSyllabi(userId);
      setSyllabi(res.syllabi || []);
    } catch {
      // Handle
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 size={14} className="animate-spin text-text-tertiary" />
      </div>
    );
  }

  if (syllabi.length === 0) {
    return (
      <p className="text-xs text-text-tertiary text-center py-3">{t.noSyllabi}</p>
    );
  }

  return (
    <div className="space-y-1.5">
      {syllabi.map((syl) => {
        const base = syl.syllabi || {};
        return (
          <button
            key={syl.id}
            onClick={() => onSelect?.(syl.syllabus_id)}
            className="w-full text-left flex items-center gap-2 px-2.5 py-2 rounded-lg
              hover:bg-surface-hover transition-colors group"
          >
            <BookOpenCheck size={12} className="text-accent-gold/60 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <span className="text-xs text-foreground truncate block">{syl.custom_title || base.title}</span>
              <span className="text-[10px] text-text-tertiary">
                {base.department} · {base.source}
              </span>
            </div>
            {syl.is_active && (
              <span className="text-[8px] bg-green-400/15 text-green-400 px-1.5 py-0.5 rounded-full font-medium">
                {t.active}
              </span>
            )}
            <ChevronRight size={10} className="text-text-tertiary group-hover:text-accent-gold" />
          </button>
        );
      })}
    </div>
  );
}
