"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Route, Plus, Trash2, GripVertical, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useHighlightStore, LearningPath } from "@/stores/highlightStore";
import { getLearningPaths, createLearningPath, deleteLearningPath, getLearningPathDetail } from "@/lib/api";

interface LearningPathPanelProps {
  userId: string;
}

export default function LearningPathPanel({ userId }: LearningPathPanelProps) {
  const { t } = useLocaleStore();
  const { learningPaths, setLearningPaths } = useHighlightStore();
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const [expandedItems, setExpandedItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadPaths();
  }, [userId]);

  const loadPaths = async () => {
    setLoading(true);
    try {
      const res = await getLearningPaths(userId);
      setLearningPaths(res.paths || []);
    } catch {
      // Handle silently
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      await createLearningPath(userId, newTitle.trim());
      setNewTitle("");
      setShowCreate(false);
      loadPaths();
    } catch {
      // Handle silently
    }
  };

  const handleDelete = async (pathId: string) => {
    try {
      await deleteLearningPath(pathId);
      setLearningPaths(learningPaths.filter((p) => p.id !== pathId));
    } catch {
      // Handle silently
    }
  };

  const toggleExpand = async (pathId: string) => {
    if (expandedPath === pathId) {
      setExpandedPath(null);
      return;
    }
    setExpandedPath(pathId);
    try {
      const res = await getLearningPathDetail(pathId);
      setExpandedItems(res.items || []);
    } catch {
      setExpandedItems([]);
    }
  };

  return (
    <div className="py-3">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Route size={14} className="text-accent-gold" />
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            {t.learningPaths}
          </h3>
        </div>
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
            <div className="flex gap-1.5">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                placeholder={t.pathName}
                className="flex-1 bg-surface-sunken border border-border-subtle rounded-lg px-2.5 py-1.5
                  text-xs text-foreground placeholder:text-text-tertiary focus:outline-none"
                autoFocus
              />
              <button
                onClick={handleCreate}
                disabled={!newTitle.trim()}
                className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-accent-gold/20 text-accent-gold
                  hover:bg-accent-gold/30 disabled:opacity-40"
              >
                {t.create}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Paths list */}
      {loading ? (
        <div className="flex justify-center py-4">
          <Loader2 size={16} className="animate-spin text-text-tertiary" />
        </div>
      ) : learningPaths.length === 0 ? (
        <p className="text-xs text-text-tertiary text-center py-3">{t.noPaths}</p>
      ) : (
        <div className="space-y-1">
          {learningPaths.map((path) => (
            <div key={path.id}>
              <div
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-hover
                  cursor-pointer transition-colors group"
                onClick={() => toggleExpand(path.id)}
              >
                <Route size={12} className="text-accent-gold/60" />
                <span className="text-xs text-foreground flex-1 truncate">{path.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(path.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 text-text-tertiary hover:text-red-400"
                >
                  <Trash2 size={10} />
                </button>
              </div>
              <AnimatePresence>
                {expandedPath === path.id && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden ml-5 space-y-0.5 mt-1 mb-1"
                  >
                    {expandedItems.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center gap-1.5 text-[11px] text-text-secondary px-2 py-1 rounded hover:bg-surface-sunken"
                      >
                        <GripVertical size={8} className="text-text-tertiary/50" />
                        <span className="px-1 py-0.5 rounded bg-surface-sunken text-[9px] uppercase text-text-tertiary">
                          {item.item_type}
                        </span>
                        <span className="truncate">{item.annotation || item.item_id.slice(0, 8)}</span>
                      </div>
                    ))}
                    {expandedItems.length === 0 && (
                      <p className="text-[10px] text-text-tertiary px-2 py-1">{t.emptyPath}</p>
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
