"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, Star, Trash2, ListPlus, FileText } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useLibraryStore, SavedPaper } from "@/stores/libraryStore";
import { updatePaperInLibrary, removePaperFromLibrary } from "@/lib/api";

interface PaperCardProps {
  paper: SavedPaper;
  userId: string;
  onAddToList?: (paperId: string) => void;
}

const STATUS_OPTIONS = ["unread", "reading", "completed", "archived"] as const;

export default function PaperCard({ paper, userId, onAddToList }: PaperCardProps) {
  const { t } = useLocaleStore();
  const { updatePaperStatus, removePaper } = useLibraryStore();
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState(paper.notes || "");
  const [rating, setRating] = useState(paper.rating || 0);

  const statusColors: Record<string, string> = {
    unread: "text-text-tertiary",
    reading: "text-accent-blue",
    completed: "text-green-400",
    archived: "text-text-tertiary opacity-60",
  };

  const handleStatusChange = async (status: SavedPaper["status"]) => {
    setShowStatusMenu(false);
    updatePaperStatus(paper.paper_id, status);
    await updatePaperInLibrary(paper.paper_id, userId, { status });
  };

  const handleRemove = async () => {
    removePaper(paper.paper_id);
    await removePaperFromLibrary(paper.paper_id, userId);
  };

  const handleRating = async (r: number) => {
    setRating(r);
    await updatePaperInLibrary(paper.paper_id, userId, { rating: r });
  };

  const handleNotesBlur = async () => {
    if (notes !== (paper.notes || "")) {
      await updatePaperInLibrary(paper.paper_id, userId, { notes });
    }
  };

  const firstAuthor = (() => {
    const authors = paper.authors;
    if (!authors || authors.length === 0) return "Unknown";
    const a = authors[0];
    return typeof a === "string" ? a : a?.name || "Unknown";
  })();

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface border border-border-subtle rounded-xl p-3 hover:border-accent-gold/30 transition-colors"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-foreground line-clamp-2 leading-snug">
            {paper.title}
          </h4>
          <p className="text-xs text-text-secondary mt-1">
            {firstAuthor} ({paper.publication_year}) · {paper.cited_by_count} {t.citations}
          </p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {/* Status dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowStatusMenu(!showStatusMenu)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider
                bg-surface-sunken ${statusColors[paper.status]}`}
            >
              {t[paper.status] || paper.status}
              <ChevronDown size={10} />
            </button>
            {showStatusMenu && (
              <div className="absolute right-0 top-full mt-1 bg-surface border border-border-subtle rounded-lg shadow-lg z-20 py-1 min-w-[120px]">
                {STATUS_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleStatusChange(s)}
                    className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-surface-hover transition-colors
                      ${paper.status === s ? "text-accent-gold" : "text-text-secondary"}`}
                  >
                    {t[s] || s}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={handleRemove} className="p-1 rounded-lg text-text-tertiary hover:text-red-400 transition-colors">
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Rating */}
      <div className="flex items-center gap-2 mt-2">
        <div className="flex gap-0.5">
          {[1, 2, 3, 4, 5].map((r) => (
            <button
              key={r}
              onClick={() => handleRating(r)}
              className={`transition-colors ${r <= rating ? "text-accent-gold" : "text-text-tertiary/30"}`}
            >
              <Star size={12} fill={r <= rating ? "currentColor" : "none"} />
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowNotes(!showNotes)}
          className="p-1 rounded text-text-tertiary hover:text-text-secondary transition-colors"
          title={t.notes}
        >
          <FileText size={12} />
        </button>
        {onAddToList && (
          <button
            onClick={() => onAddToList(paper.paper_id)}
            className="p-1 rounded text-text-tertiary hover:text-text-secondary transition-colors"
            title={t.addToList}
          >
            <ListPlus size={12} />
          </button>
        )}
      </div>

      {/* Notes */}
      {showNotes && (
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={handleNotesBlur}
          placeholder={t.addNotes}
          className="w-full mt-2 bg-surface-sunken border border-border-subtle rounded-lg px-3 py-2
            text-xs text-foreground placeholder:text-text-tertiary resize-none focus:outline-none focus:border-accent-gold/40"
          rows={2}
        />
      )}

      {/* Tags */}
      {paper.tags && paper.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {paper.tags.map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded-full bg-accent-gold/10 text-accent-gold text-[10px]"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}
