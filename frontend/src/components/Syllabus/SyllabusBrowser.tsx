"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Search, GraduationCap, ChevronRight, Loader2, X, GitFork } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getSyllabi, getSyllabusDetail, forkSyllabus } from "@/lib/api";
import SyllabusDetail from "./SyllabusDetail";

interface SyllabusBrowserProps {
  userId?: string;
  onClose: () => void;
}

const SOURCES = [
  { key: null, label: "all" },
  { key: "mit_ocw", label: "MIT OCW" },
  { key: "openstax", label: "OpenStax" },
  { key: "custom", label: "Custom" },
];

export default function SyllabusBrowser({ userId, onClose }: SyllabusBrowserProps) {
  const { t } = useLocaleStore();
  const [syllabi, setSyllabi] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [selectedSyllabus, setSelectedSyllabus] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    loadSyllabi();
  }, [sourceFilter]);

  const loadSyllabi = async () => {
    setLoading(true);
    try {
      const res = await getSyllabi(search || undefined, undefined, sourceFilter || undefined);
      setSyllabi(res.syllabi || []);
    } catch {
      setSyllabi([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => loadSyllabi();

  const handleSelect = async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await getSyllabusDetail(id);
      setSelectedSyllabus(res);
    } catch {
      // Handle
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleFork = async (syllabusId: string) => {
    if (!userId) return;
    try {
      await forkSyllabus(syllabusId, userId);
    } catch {
      // Handle
    }
  };

  if (selectedSyllabus) {
    return (
      <SyllabusDetail
        syllabus={selectedSyllabus}
        userId={userId}
        onBack={() => setSelectedSyllabus(null)}
        onFork={handleFork}
      />
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-full"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <GraduationCap size={16} className="text-accent-gold" />
          <h2 className="text-sm font-semibold text-foreground">{t.syllabi}</h2>
        </div>
        <button onClick={onClose} className="p-1 rounded-lg hover:bg-surface-hover text-text-tertiary">
          <X size={16} />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-border space-y-2">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder={t.searchSyllabi}
            className="w-full bg-surface-sunken border border-border-subtle rounded-lg pl-8 pr-3 py-1.5
              text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold/40"
          />
        </div>
        <div className="flex gap-1">
          {SOURCES.map((s) => (
            <button
              key={s.key ?? "all"}
              onClick={() => setSourceFilter(s.key)}
              className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                sourceFilter === s.key
                  ? "bg-accent-gold/20 text-accent-gold"
                  : "bg-surface-sunken text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {s.label === "all" ? t.all : s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Syllabus list */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={20} className="animate-spin text-text-tertiary" />
          </div>
        ) : syllabi.length === 0 ? (
          <p className="text-xs text-text-tertiary text-center py-6">{t.noData}</p>
        ) : (
          syllabi.map((syl) => (
            <button
              key={syl.id}
              onClick={() => handleSelect(syl.id)}
              className="w-full text-left bg-surface border border-border-subtle rounded-lg p-3
                hover:border-accent-gold/30 transition-colors group"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h4 className="text-xs font-medium text-foreground line-clamp-1">{syl.title}</h4>
                  <p className="text-[10px] text-text-tertiary mt-0.5">
                    {syl.institution} · {syl.department}
                  </p>
                  {syl.instructor && (
                    <p className="text-[10px] text-text-tertiary">{syl.instructor}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-[9px] text-text-tertiary bg-surface-sunken px-1.5 py-0.5 rounded">
                    {syl.source}
                  </span>
                  <ChevronRight size={12} className="text-text-tertiary group-hover:text-accent-gold" />
                </div>
              </div>
              {syl.paper_count > 0 && (
                <p className="text-[10px] text-text-tertiary mt-1">
                  {syl.paper_count} {t.papers}
                </p>
              )}
            </button>
          ))
        )}
      </div>
    </motion.div>
  );
}
