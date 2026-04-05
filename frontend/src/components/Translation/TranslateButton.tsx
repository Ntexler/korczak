"use client";

import { useState } from "react";
import { Languages, Loader2 } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface TranslateButtonProps {
  paperId: string;
  sourceLanguage?: string;
  onTranslated: (translation: {
    translated_title: string;
    translated_abstract?: string;
  }) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function TranslateButton({ paperId, sourceLanguage, onTranslated }: TranslateButtonProps) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const { locale } = useLocaleStore();

  // Don't show if paper is already in user's language
  if (sourceLanguage === locale) return null;

  const handleTranslate = async () => {
    if (loading || done) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/translation/translate?paper_id=${paperId}&target_lang=${locale}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      onTranslated(data);
      setDone(true);
    } catch (err) {
      console.error("Translation error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleTranslate}
      disabled={loading}
      className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium text-accent-gold hover:bg-accent-gold/10 transition-colors disabled:opacity-50"
      title={locale === "he" ? "תרגם לעברית" : "Translate to English"}
    >
      {loading ? (
        <Loader2 size={12} className="animate-spin" />
      ) : (
        <Languages size={12} />
      )}
      <span>
        {done
          ? (locale === "he" ? "תורגם" : "Translated")
          : (locale === "he" ? "תרגם" : "Translate")
        }
      </span>
    </button>
  );
}
