"use client";

import { useState } from "react";
import { Eye, EyeOff, Flag } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface TranslatedViewProps {
  originalTitle: string;
  originalAbstract?: string;
  translatedTitle: string;
  translatedAbstract?: string;
  sourceLanguage?: string;
  translationId?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function TranslatedView({
  originalTitle,
  originalAbstract,
  translatedTitle,
  translatedAbstract,
  sourceLanguage,
  translationId,
}: TranslatedViewProps) {
  const [showOriginal, setShowOriginal] = useState(false);
  const [flagged, setFlagged] = useState(false);
  const { locale } = useLocaleStore();

  const handleFlag = async () => {
    if (!translationId || flagged) return;
    try {
      await fetch(`${API_BASE}/translation/${translationId}/flag`, { method: "POST" });
      setFlagged(true);
    } catch {
      // Silently fail
    }
  };

  return (
    <div className="space-y-2">
      {/* Toggle bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setShowOriginal(!showOriginal)}
          className="flex items-center gap-1.5 text-[10px] text-text-tertiary hover:text-text-secondary transition-colors"
        >
          {showOriginal ? <EyeOff size={10} /> : <Eye size={10} />}
          <span>
            {showOriginal
              ? (locale === "he" ? "הסתר מקור" : "Hide original")
              : (locale === "he" ? "הצג מקור" : "Show original")
            }
          </span>
          {sourceLanguage && (
            <span className="px-1 py-0.5 rounded bg-surface-sunken text-[9px] uppercase">
              {sourceLanguage}
            </span>
          )}
        </button>
        {translationId && (
          <button
            onClick={handleFlag}
            className={`flex items-center gap-1 text-[10px] transition-colors ${
              flagged ? "text-accent-red" : "text-text-tertiary hover:text-accent-red"
            }`}
            title={locale === "he" ? "דווח על תרגום לקוי" : "Flag poor translation"}
          >
            <Flag size={9} />
            <span>{flagged ? (locale === "he" ? "דווח" : "Flagged") : (locale === "he" ? "דווח" : "Flag")}</span>
          </button>
        )}
      </div>

      {/* Translated content */}
      <div>
        <h4 className="text-sm font-semibold text-foreground">{translatedTitle}</h4>
        {translatedAbstract && (
          <p className="text-xs text-text-secondary leading-relaxed mt-1">{translatedAbstract}</p>
        )}
      </div>

      {/* Original content (togglable) */}
      {showOriginal && (
        <div className="border-t border-border/50 pt-2 mt-2">
          <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">
            {locale === "he" ? "מקור" : "Original"} ({sourceLanguage || "?"})
          </p>
          <h4 className="text-sm text-text-secondary">{originalTitle}</h4>
          {originalAbstract && (
            <p className="text-xs text-text-tertiary leading-relaxed mt-1">{originalAbstract}</p>
          )}
        </div>
      )}
    </div>
  );
}
