"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { MapPin, Loader2, CheckCircle2, Circle } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getSyllabusProgress } from "@/lib/api";

interface SyllabusProgressProps {
  syllabusId: string;
  userId: string;
}

export default function SyllabusProgress({ syllabusId, userId }: SyllabusProgressProps) {
  const { t } = useLocaleStore();
  const [progress, setProgress] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProgress();
  }, [syllabusId, userId]);

  const loadProgress = async () => {
    setLoading(true);
    try {
      const res = await getSyllabusProgress(syllabusId, userId);
      setProgress(res);
    } catch {
      // Handle
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 size={16} className="animate-spin text-text-tertiary" />
      </div>
    );
  }

  if (!progress) return null;

  return (
    <div className="py-3">
      <div className="flex items-center gap-2 mb-3">
        <MapPin size={14} className="text-accent-gold" />
        <h3 className="text-xs font-semibold text-accent-gold uppercase tracking-wider">
          {t.whereAmI}
        </h3>
      </div>

      {/* Progress bar */}
      <div className="bg-surface-sunken rounded-full h-2 mb-2">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${progress.completion_pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="bg-accent-gold rounded-full h-2"
        />
      </div>
      <p className="text-[10px] text-text-tertiary mb-3">
        {progress.completed_readings}/{progress.total_readings} {t.completed} ({progress.completion_pct}%)
      </p>

      {/* Reading checklist */}
      <div className="space-y-1 max-h-[200px] overflow-y-auto">
        {(progress.readings || []).map((r: any) => {
          const done = progress.progress?.[r.id]?.status === "completed";
          return (
            <div key={r.id} className="flex items-center gap-2 px-2 py-1 rounded text-[11px]">
              {done ? (
                <CheckCircle2 size={11} className="text-green-400 flex-shrink-0" />
              ) : (
                <Circle size={11} className="text-text-tertiary/40 flex-shrink-0" />
              )}
              <span className={`truncate ${done ? "text-text-tertiary line-through" : "text-foreground"}`}>
                {r.external_title || `Week ${r.week}`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
