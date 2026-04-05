"use client";

import { useState } from "react";
import { BookmarkPlus, BookmarkCheck, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { savePaperToLibrary, removePaperFromLibrary } from "@/lib/api";

interface SavePaperButtonProps {
  paperId: string;
  userId?: string;
  isSaved?: boolean;
  saveContext?: string;
  size?: number;
  onToggle?: (saved: boolean) => void;
}

export default function SavePaperButton({
  paperId,
  userId,
  isSaved = false,
  saveContext = "browsing",
  size = 16,
  onToggle,
}: SavePaperButtonProps) {
  const [saved, setSaved] = useState(isSaved);
  const [loading, setLoading] = useState(false);
  const { t } = useLocaleStore();

  const handleToggle = async () => {
    if (!userId) return;
    setLoading(true);
    try {
      if (saved) {
        await removePaperFromLibrary(paperId, userId);
        setSaved(false);
        onToggle?.(false);
      } else {
        await savePaperToLibrary(userId, paperId, saveContext);
        setSaved(true);
        onToggle?.(true);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <button disabled className="p-1.5 rounded-lg text-text-tertiary">
        <Loader2 size={size} className="animate-spin" />
      </button>
    );
  }

  return (
    <button
      onClick={handleToggle}
      className={`p-1.5 rounded-lg transition-colors ${
        saved
          ? "text-accent-gold hover:text-accent-gold/70"
          : "text-text-tertiary hover:text-accent-gold"
      }`}
      title={saved ? t.removeFromLibrary : t.savePaper}
    >
      {saved ? <BookmarkCheck size={size} /> : <BookmarkPlus size={size} />}
    </button>
  );
}
