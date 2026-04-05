"use client";

import { motion } from "framer-motion";
import { ArrowLeft, GitFork, CheckCircle2, Circle, BookOpen } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface SyllabusDetailProps {
  syllabus: any;
  userId?: string;
  onBack: () => void;
  onFork: (syllabusId: string) => void;
}

export default function SyllabusDetail({ syllabus, userId, onBack, onFork }: SyllabusDetailProps) {
  const { t } = useLocaleStore();
  const weeks = syllabus.readings_by_week || {};

  return (
    <motion.div
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="flex flex-col h-full"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-border">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-text-secondary hover:text-foreground mb-2"
        >
          <ArrowLeft size={12} />
          {t.back}
        </button>
        <h2 className="text-sm font-semibold text-foreground">{syllabus.title}</h2>
        <p className="text-[10px] text-text-tertiary mt-0.5">
          {syllabus.institution} · {syllabus.department}
          {syllabus.instructor && ` · ${syllabus.instructor}`}
        </p>
        {userId && (
          <button
            onClick={() => onFork(syllabus.id)}
            className="mt-2 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
              bg-accent-gold/20 text-accent-gold hover:bg-accent-gold/30 transition-colors"
          >
            <GitFork size={12} />
            {t.forkSyllabus}
          </button>
        )}
      </div>

      {/* Readings by week */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {Object.keys(weeks).length === 0 ? (
          <p className="text-xs text-text-tertiary text-center py-6">{t.noData}</p>
        ) : (
          Object.entries(weeks)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([week, readings]: [string, any]) => (
              <div key={week}>
                <h3 className="text-[10px] font-semibold text-accent-gold uppercase tracking-wider mb-2">
                  {t.week} {week}
                </h3>
                <div className="space-y-1.5">
                  {readings.map((r: any) => (
                    <div
                      key={r.id}
                      className="flex items-start gap-2 px-2.5 py-2 rounded-lg bg-surface-sunken"
                    >
                      {r.paper ? (
                        <CheckCircle2 size={12} className="text-green-400 mt-0.5 flex-shrink-0" />
                      ) : (
                        <Circle size={12} className="text-text-tertiary/40 mt-0.5 flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-foreground line-clamp-2">
                          {r.paper?.title || r.external_title || "Untitled"}
                        </p>
                        {r.external_authors && (
                          <p className="text-[10px] text-text-tertiary mt-0.5">
                            {r.external_authors} {r.external_year && `(${r.external_year})`}
                          </p>
                        )}
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[9px] px-1 py-0.5 rounded ${
                            r.section === "required"
                              ? "bg-accent-gold/10 text-accent-gold"
                              : r.section === "recommended"
                                ? "bg-accent-blue/10 text-accent-blue"
                                : "bg-surface text-text-tertiary"
                          }`}>
                            {r.section}
                          </span>
                          {r.match_confidence > 0 && (
                            <span className="text-[9px] text-text-tertiary">
                              {Math.round(r.match_confidence * 100)}% match
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
        )}
      </div>
    </motion.div>
  );
}
