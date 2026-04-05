"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { Sparkles, BookmarkPlus, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useLibraryStore } from "@/stores/libraryStore";
import { getLibraryRecommendations, savePaperToLibrary } from "@/lib/api";
import SavePaperButton from "./SavePaperButton";

interface RecommendationFeedProps {
  userId: string;
}

export default function RecommendationFeed({ userId }: RecommendationFeedProps) {
  const { t } = useLocaleStore();
  const { recommendations, isLoadingRecs, setRecommendations, setLoadingRecs } = useLibraryStore();

  useEffect(() => {
    loadRecommendations();
  }, [userId]);

  const loadRecommendations = async () => {
    setLoadingRecs(true);
    try {
      const res = await getLibraryRecommendations(userId);
      setRecommendations(res.recommendations || []);
    } catch {
      // Silently handle
    } finally {
      setLoadingRecs(false);
    }
  };

  if (isLoadingRecs) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 size={18} className="animate-spin text-text-tertiary" />
      </div>
    );
  }

  if (recommendations.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={14} className="text-accent-gold" />
        <h3 className="text-xs font-semibold text-accent-gold uppercase tracking-wider">
          {t.suggestedForYou}
        </h3>
      </div>
      <div className="space-y-2">
        {recommendations.slice(0, 5).map((rec, i) => (
          <motion.div
            key={rec.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="bg-surface-sunken border border-border-subtle rounded-lg p-2.5 hover:border-accent-gold/20 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <h4 className="text-xs font-medium text-foreground line-clamp-2">
                  {rec.title}
                </h4>
                <p className="text-[10px] text-text-tertiary mt-0.5">
                  {rec.publication_year} · {rec.cited_by_count} {t.citations}
                </p>
                <p className="text-[10px] text-accent-gold/80 mt-1 italic">
                  {rec.reason}
                </p>
              </div>
              <SavePaperButton
                paperId={rec.id}
                userId={userId}
                saveContext="recommendation"
                size={14}
                onToggle={() => loadRecommendations()}
              />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
