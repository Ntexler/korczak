"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Search, X, FileText, Lightbulb, BookOpen, Filter, ArrowRight } from "lucide-react";
import { searchConcepts } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";

interface GlobalSearchProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
}

const CONCEPT_TYPE_COLORS: Record<string, string> = {
  theory: "#E8B931",
  method: "#58A6FF",
  framework: "#3FB950",
  phenomenon: "#D29922",
  tool: "#BC8CFF",
  metric: "#F78166",
  critique: "#F85149",
  paradigm: "#E8B931",
};

export default function GlobalSearch({ isOpen, onClose, onSend }: GlobalSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { setSelectedConceptId, setConceptPanelOpen } = useChatStore();
  const { locale, t } = useLocaleStore();

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
    }
  }, [isOpen]);

  // Keyboard shortcut: Cmd+K or Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isOpen) onClose();
        else onClose(); // toggle handled by parent
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  // Debounced search
  const searchTimeout = useRef<NodeJS.Timeout>(null);
  const handleSearch = useCallback((value: string) => {
    setQuery(value);
    setSelectedIndex(0);

    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    if (value.length < 2) {
      setResults([]);
      return;
    }

    searchTimeout.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await searchConcepts(value);
        let filtered = data || [];
        if (typeFilter) {
          filtered = filtered.filter((c: any) => c.type === typeFilter);
        }
        setResults(filtered.slice(0, 20));
      } catch {
        setResults([]);
      }
      setLoading(false);
    }, 200);
  }, [typeFilter]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIndex === 0 && query.length > 0) {
        // Ask Korczak
        onSend(query);
        onClose();
      } else if (results[selectedIndex - 1]) {
        selectConcept(results[selectedIndex - 1]);
      }
    }
  };

  const selectConcept = (concept: any) => {
    setSelectedConceptId(concept.id);
    setConceptPanelOpen(true);
    onClose();
  };

  const askKorczak = () => {
    if (query.trim()) {
      onSend(query.trim());
      onClose();
    }
  };

  if (!isOpen) return null;

  const typeFilters = ["theory", "method", "framework", "phenomenon", "tool", "critique"];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Search modal */}
      <div className="relative w-full max-w-[640px] mx-4 bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
          <Search size={18} className="text-text-tertiary flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={locale === "he"
              ? "חפש קונספטים, מאמרים, או שאל את קורצאק..."
              : "Search concepts, papers, or ask Korczak..."
            }
            className="flex-1 bg-transparent text-foreground text-base placeholder:text-text-tertiary focus:outline-none"
          />
          <kbd className="hidden sm:flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-surface-sunken border border-border text-[10px] text-text-tertiary">
            ESC
          </kbd>
          <button onClick={onClose} className="p-1 rounded hover:bg-surface-hover text-text-tertiary">
            <X size={16} />
          </button>
        </div>

        {/* Type filters */}
        <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-border/50 overflow-x-auto">
          <Filter size={12} className="text-text-tertiary flex-shrink-0" />
          <button
            onClick={() => { setTypeFilter(null); handleSearch(query); }}
            className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-colors ${
              !typeFilter
                ? "bg-accent-gold/15 text-accent-gold"
                : "text-text-tertiary hover:text-text-secondary hover:bg-surface-hover"
            }`}
          >
            {locale === "he" ? "הכל" : "All"}
          </button>
          {typeFilters.map((type) => (
            <button
              key={type}
              onClick={() => { setTypeFilter(typeFilter === type ? null : type); handleSearch(query); }}
              className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-colors flex items-center gap-1 ${
                typeFilter === type
                  ? "bg-accent-gold/15 text-accent-gold"
                  : "text-text-tertiary hover:text-text-secondary hover:bg-surface-hover"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: CONCEPT_TYPE_COLORS[type] }} />
              {type}
            </button>
          ))}
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto">
          {/* Ask Korczak option — always first */}
          {query.length > 0 && (
            <button
              onClick={askKorczak}
              className={`w-full flex items-center gap-3 px-5 py-3 text-left transition-colors ${
                selectedIndex === 0 ? "bg-accent-gold/10" : "hover:bg-surface-hover"
              }`}
            >
              <div className="w-8 h-8 rounded-full bg-accent-gold-dim flex items-center justify-center flex-shrink-0">
                <Lightbulb size={14} className="text-accent-gold" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-foreground font-medium">
                  {locale === "he" ? `שאל את קורצאק: "${query}"` : `Ask Korczak: "${query}"`}
                </div>
                <div className="text-xs text-text-tertiary">
                  {locale === "he" ? "חיפוש חכם עם ניתוח ומקורות" : "Smart search with analysis and sources"}
                </div>
              </div>
              <ArrowRight size={14} className="text-text-tertiary" />
            </button>
          )}

          {/* Loading */}
          {loading && (
            <div className="px-5 py-4 text-xs text-text-tertiary">
              {locale === "he" ? "מחפש..." : "Searching..."}
            </div>
          )}

          {/* Concept results */}
          {results.map((concept, i) => (
            <button
              key={concept.id}
              onClick={() => selectConcept(concept)}
              className={`w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors ${
                selectedIndex === i + 1 ? "bg-surface-hover" : "hover:bg-surface-hover/50"
              }`}
            >
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: CONCEPT_TYPE_COLORS[concept.type] || "#8B949E" }}
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm text-foreground">{concept.name}</div>
                <div className="text-xs text-text-tertiary truncate">
                  {concept.type} {concept.definition ? `— ${concept.definition.slice(0, 80)}...` : ""}
                </div>
              </div>
              {concept.paper_count > 0 && (
                <div className="flex items-center gap-1 text-[10px] text-text-tertiary flex-shrink-0">
                  <FileText size={10} />
                  {concept.paper_count}
                </div>
              )}
            </button>
          ))}

          {/* Empty state */}
          {!loading && query.length >= 2 && results.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-text-tertiary">
              {locale === "he"
                ? `לא נמצאו תוצאות ל-"${query}". לחץ Enter לשאול את קורצאק.`
                : `No results for "${query}". Press Enter to ask Korczak.`
              }
            </div>
          )}

          {/* Quick prompts when empty */}
          {query.length === 0 && (
            <div className="px-5 py-4 space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-3">
                {locale === "he" ? "נסה לשאול" : "Try asking"}
              </div>
              {[
                locale === "he" ? "מה ההבדל בין אתנוגרפיה למתודולוגיה?" : "What's the difference between ethnography and methodology?",
                locale === "he" ? "הראה לי מחלוקות פעילות באנתרופולוגיה" : "Show me active debates in anthropology",
                locale === "he" ? "מהם הקונספטים הבסיסיים בתחום השינה?" : "What are foundational concepts in sleep research?",
              ].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => { onSend(prompt); onClose(); }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm
                    text-text-secondary hover:text-foreground hover:bg-surface-hover transition-colors"
                >
                  <BookOpen size={12} className="text-accent-gold/50 flex-shrink-0" />
                  <span className="truncate">{prompt}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-2.5 border-t border-border/50 text-[10px] text-text-tertiary">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded bg-surface-sunken border border-border">↑↓</kbd>
              {locale === "he" ? "ניווט" : "navigate"}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded bg-surface-sunken border border-border">↵</kbd>
              {locale === "he" ? "בחירה" : "select"}
            </span>
          </div>
          <span>{results.length > 0 ? `${results.length} ${locale === "he" ? "תוצאות" : "results"}` : ""}</span>
        </div>
      </div>
    </div>
  );
}
