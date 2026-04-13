"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Concept {
  id: string;
  name: string;
  status: "not_started" | "in_progress" | "done";
}

interface Week {
  week_number: number;
  title: string;
  concepts: Concept[];
}

interface SyllabusNavProps {
  field: string;
  onSelectConcept: (id: string) => void;
}

function statusDot(status: Concept["status"]) {
  switch (status) {
    case "done":
      return <span className="text-accent-green text-xs" title="Done">&#x25CF;</span>;
    case "in_progress":
      return <span className="text-accent-gold text-xs" title="In progress">&#x25D1;</span>;
    default:
      return <span className="text-text-tertiary text-xs" title="Not started">&#x25CB;</span>;
  }
}

export default function SyllabusNav({ field, onSelectConcept }: SyllabusNavProps) {
  const { t } = useLocaleStore();
  const [weeks, setWeeks] = useState<Week[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/features/fields/${encodeURIComponent(field)}/syllabus`
        );
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const data = await res.json();
        const weekList: Week[] = Array.isArray(data) ? data : data.weeks ?? [];
        if (!cancelled) {
          setWeeks(weekList);
          // Auto-expand first week
          if (weekList.length > 0) {
            setExpanded(new Set([weekList[0].week_number]));
          }
        }
      } catch {
        if (!cancelled) setWeeks([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [field]);

  const toggleWeek = (num: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  const weekProgress = (week: Week): string => {
    if (week.concepts.length === 0) return "";
    const done = week.concepts.filter((c) => c.status === "done").length;
    return `${done}/${week.concepts.length}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        Loading syllabus...
      </div>
    );
  }

  if (weeks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm px-4 text-center">
        No syllabus available for this field
      </div>
    );
  }

  return (
    <nav className="h-full overflow-y-auto py-3">
      <h2 className="section-header px-4 mb-3">Syllabus</h2>
      <ul className="space-y-0.5">
        {weeks.map((week) => {
          const isOpen = expanded.has(week.week_number);
          return (
            <li key={week.week_number}>
              <button
                onClick={() => toggleWeek(week.week_number)}
                className="w-full flex items-center gap-2 px-4 py-2 text-left
                           hover:bg-surface-hover transition-colors group"
              >
                {isOpen ? (
                  <ChevronDown size={14} className="text-text-tertiary flex-shrink-0" />
                ) : (
                  <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />
                )}
                <span className="flex-1 text-sm text-foreground truncate">
                  {t.week} {week.week_number}: {week.title}
                </span>
                <span className="text-xs text-text-tertiary tabular-nums">
                  {weekProgress(week)}
                </span>
              </button>

              {isOpen && week.concepts.length > 0 && (
                <ul className="ml-6 border-l border-border-subtle">
                  {week.concepts.map((concept) => (
                    <li key={concept.id}>
                      <button
                        onClick={() => onSelectConcept(concept.id)}
                        className="w-full flex items-center gap-2 pl-4 pr-4 py-1.5 text-left
                                   hover:bg-surface-hover transition-colors group"
                      >
                        {statusDot(concept.status)}
                        <span className="text-sm text-text-secondary group-hover:text-accent-gold transition-colors truncate">
                          {concept.name}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
