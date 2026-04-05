"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Search, Filter, X, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useLibraryStore } from "@/stores/libraryStore";
import { getLibraryPapers } from "@/lib/api";
import PaperCard from "./PaperCard";
import ReadingListManager from "./ReadingListManager";
import RecommendationFeed from "./RecommendationFeed";

interface PaperLibraryProps {
  userId: string;
  onClose: () => void;
}

const STATUS_FILTERS = [
  { key: null, icon: "all" },
  { key: "unread", icon: "unread" },
  { key: "reading", icon: "reading" },
  { key: "completed", icon: "completed" },
  { key: "archived", icon: "archived" },
] as const;

export default function PaperLibrary({ userId, onClose }: PaperLibraryProps) {
  const { t } = useLocaleStore();
  const {
    papers, isLoadingPapers, statusFilter, searchQuery,
    setPapers, setLoadingPapers, setStatusFilter, setSearchQuery,
  } = useLibraryStore();
  const [activeTab, setActiveTab] = useState<"papers" | "lists">("papers");

  useEffect(() => {
    loadPapers();
  }, [userId, statusFilter]);

  const loadPapers = async () => {
    setLoadingPapers(true);
    try {
      const res = await getLibraryPapers(userId, statusFilter || undefined);
      setPapers(res.papers || []);
    } catch {
      // Handle silently
    } finally {
      setLoadingPapers(false);
    }
  };

  const filteredPapers = papers.filter((p) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.title?.toLowerCase().includes(q) ||
      p.notes?.toLowerCase().includes(q)
    );
  });

  return (
    <motion.aside
      initial={{ x: -280, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -280, opacity: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="w-[320px] border-r border-border bg-background flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <BookOpen size={16} className="text-accent-gold" />
          <h2 className="text-sm font-semibold text-foreground">{t.library}</h2>
        </div>
        <button onClick={onClose} className="p-1 rounded-lg hover:bg-surface-hover text-text-tertiary">
          <X size={16} />
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border">
        {(["papers", "lists"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              activeTab === tab
                ? "text-accent-gold border-b-2 border-accent-gold"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {tab === "papers" ? t.myPapers : t.readingLists}
          </button>
        ))}
      </div>

      {activeTab === "papers" ? (
        <>
          {/* Search + Filters */}
          <div className="px-3 py-2 border-b border-border space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t.searchLibrary}
                className="w-full bg-surface-sunken border border-border-subtle rounded-lg pl-8 pr-3 py-1.5
                  text-xs text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold/40"
              />
            </div>
            <div className="flex gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key ?? "all"}
                  onClick={() => setStatusFilter(f.key)}
                  className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                    statusFilter === f.key
                      ? "bg-accent-gold/20 text-accent-gold"
                      : "bg-surface-sunken text-text-tertiary hover:text-text-secondary"
                  }`}
                >
                  {t[f.key ?? "all"] || f.key || t.all}
                </button>
              ))}
            </div>
          </div>

          {/* Paper list */}
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
            {isLoadingPapers ? (
              <div className="flex justify-center py-8">
                <Loader2 size={20} className="animate-spin text-text-tertiary" />
              </div>
            ) : filteredPapers.length === 0 ? (
              <div className="text-center py-8">
                <BookOpen size={24} className="mx-auto text-text-tertiary/50 mb-2" />
                <p className="text-xs text-text-tertiary">{t.emptyLibrary}</p>
              </div>
            ) : (
              filteredPapers.map((paper) => (
                <PaperCard key={paper.paper_id} paper={paper} userId={userId} />
              ))
            )}

            {/* Recommendations */}
            <RecommendationFeed userId={userId} />
          </div>
        </>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-2">
          <ReadingListManager userId={userId} />
        </div>
      )}
    </motion.aside>
  );
}
