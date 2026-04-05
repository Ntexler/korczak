"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, ChevronRight, Palette, Trash2, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useLibraryStore, ReadingList } from "@/stores/libraryStore";
import {
  getReadingLists,
  createReadingList,
  deleteReadingList,
  getReadingListDetail,
} from "@/lib/api";

interface ReadingListManagerProps {
  userId: string;
}

const LIST_COLORS = ["#E8B931", "#58A6FF", "#3FB950", "#BC8CFF", "#F78166", "#D29922"];

export default function ReadingListManager({ userId }: ReadingListManagerProps) {
  const { t } = useLocaleStore();
  const { readingLists, isLoadingLists, setReadingLists, setLoadingLists } = useLibraryStore();
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newColor, setNewColor] = useState(LIST_COLORS[0]);
  const [expandedList, setExpandedList] = useState<string | null>(null);
  const [expandedPapers, setExpandedPapers] = useState<any[]>([]);

  useEffect(() => {
    loadLists();
  }, [userId]);

  const loadLists = async () => {
    setLoadingLists(true);
    try {
      const res = await getReadingLists(userId);
      setReadingLists(res.lists || []);
    } catch {
      // Silently handle
    } finally {
      setLoadingLists(false);
    }
  };

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      await createReadingList(userId, newTitle.trim(), undefined, newColor);
      setNewTitle("");
      setShowCreate(false);
      loadLists();
    } catch {
      // Silently handle
    }
  };

  const handleDelete = async (listId: string) => {
    try {
      await deleteReadingList(listId);
      setReadingLists(readingLists.filter((l) => l.id !== listId));
      if (expandedList === listId) setExpandedList(null);
    } catch {
      // Silently handle
    }
  };

  const toggleExpand = async (listId: string) => {
    if (expandedList === listId) {
      setExpandedList(null);
      return;
    }
    setExpandedList(listId);
    try {
      const res = await getReadingListDetail(listId);
      setExpandedPapers(res.papers || []);
    } catch {
      setExpandedPapers([]);
    }
  };

  const getPaperCount = (list: ReadingList) => {
    if (list.reading_list_papers && list.reading_list_papers.length > 0) {
      return list.reading_list_papers[0]?.count || 0;
    }
    return 0;
  };

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {t.readingLists}
        </h3>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="p-1 rounded-lg text-text-tertiary hover:text-accent-gold transition-colors"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Create form */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-3 overflow-hidden"
          >
            <div className="bg-surface-sunken border border-border-subtle rounded-lg p-2.5">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                placeholder={t.listName}
                className="w-full bg-transparent text-sm text-foreground placeholder:text-text-tertiary
                  focus:outline-none mb-2"
                autoFocus
              />
              <div className="flex items-center justify-between">
                <div className="flex gap-1">
                  {LIST_COLORS.map((c) => (
                    <button
                      key={c}
                      onClick={() => setNewColor(c)}
                      className={`w-4 h-4 rounded-full transition-transform ${
                        newColor === c ? "scale-125 ring-1 ring-white/30" : ""
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
                <button
                  onClick={handleCreate}
                  disabled={!newTitle.trim()}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium bg-accent-gold/20 text-accent-gold
                    hover:bg-accent-gold/30 disabled:opacity-40 transition-colors"
                >
                  {t.create}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Lists */}
      {isLoadingLists ? (
        <div className="flex justify-center py-4">
          <Loader2 size={16} className="animate-spin text-text-tertiary" />
        </div>
      ) : readingLists.length === 0 ? (
        <p className="text-xs text-text-tertiary text-center py-3">{t.noLists}</p>
      ) : (
        <div className="space-y-1.5">
          {readingLists.map((list) => (
            <div key={list.id}>
              <div
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg hover:bg-surface-hover
                  cursor-pointer transition-colors group"
                onClick={() => toggleExpand(list.id)}
              >
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: list.color }} />
                <ChevronRight
                  size={12}
                  className={`text-text-tertiary transition-transform ${
                    expandedList === list.id ? "rotate-90" : ""
                  }`}
                />
                <span className="text-xs text-foreground flex-1 truncate">{list.title}</span>
                <span className="text-[10px] text-text-tertiary">{getPaperCount(list)}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(list.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 text-text-tertiary hover:text-red-400 transition-all"
                >
                  <Trash2 size={10} />
                </button>
              </div>
              {/* Expanded papers */}
              <AnimatePresence>
                {expandedList === list.id && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden ml-5 space-y-1 mt-1"
                  >
                    {expandedPapers.map((paper) => (
                      <div key={paper.id} className="text-[11px] text-text-secondary px-2 py-1 rounded hover:bg-surface-sunken">
                        {paper.title?.slice(0, 60)}{paper.title?.length > 60 ? "..." : ""}
                      </div>
                    ))}
                    {expandedPapers.length === 0 && (
                      <p className="text-[10px] text-text-tertiary px-2 py-1">{t.emptyList}</p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
