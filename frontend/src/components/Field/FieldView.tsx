"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Search,
  Settings,
  GraduationCap,
  FlaskConical,
  Compass,
  Download,
  Check,
  Loader2,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useFieldStore } from "@/stores/fieldStore";
import { exportFieldToObsidian } from "@/lib/api";
import SyllabusNav from "./SyllabusNav";
import ContentPanel from "./ContentPanel";
import ProgressBar from "./ProgressBar";

interface FieldViewProps {
  field: string;
  onBack: () => void;
  onSend: (text: string) => void;
}

const MODE_CONFIG = {
  learn: { label: "Learn", icon: GraduationCap },
  research: { label: "Research", icon: FlaskConical },
  discover: { label: "Discover", icon: Compass },
} as const;

type FieldMode = "learn" | "research" | "discover";

export default function FieldView({ field, onBack, onSend }: FieldViewProps) {
  const { fonts: f, locale } = useLocaleStore();
  const { currentMode, setMode } = useFieldStore();
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [fieldExporting, setFieldExporting] = useState(false);
  const [fieldExported, setFieldExported] = useState(false);

  // Placeholder userId — should come from auth context in production
  const userId = "mock-user";

  const handleExportField = async () => {
    if (fieldExporting) return;
    setFieldExporting(true);
    try {
      const blob = await exportFieldToObsidian(field);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeName = field.replace(/\s+/g, "_").replace(/&/g, "and");
      a.download = `Korczak_${safeName}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setFieldExported(true);
      setTimeout(() => setFieldExported(false), 3000);
    } catch (e) {
      console.error("Field export failed:", e);
    } finally {
      setFieldExporting(false);
    }
  };

  const handleSearchSubmit = () => {
    if (searchQuery.trim()) {
      onSend(searchQuery.trim());
      setSearchQuery("");
      setSearchOpen(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ---- Header ---- */}
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-surface shrink-0">
        {/* Back */}
        <button
          onClick={onBack}
          className="p-1.5 rounded-md hover:bg-surface-hover transition-colors text-text-secondary hover:text-foreground"
          title="Back"
        >
          <ArrowLeft size={18} />
        </button>

        {/* Field name */}
        <h1
          className="text-base font-semibold text-foreground truncate"
          style={{ fontFamily: f.display }}
        >
          {field}
        </h1>

        {/* Mode toggle */}
        <div className="flex items-center rounded-lg border border-border bg-surface-sunken ml-auto">
          {(Object.keys(MODE_CONFIG) as FieldMode[]).map((mode) => {
            const cfg = MODE_CONFIG[mode];
            const Icon = cfg.icon;
            const active = currentMode === mode;
            return (
              <button
                key={mode}
                onClick={() => setMode(mode)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors rounded-md
                  ${
                    active
                      ? "bg-accent-gold/10 text-accent-gold"
                      : "text-text-tertiary hover:text-text-secondary"
                  }`}
                title={cfg.label}
              >
                <Icon size={13} />
                <span className="hidden sm:inline">{cfg.label}</span>
              </button>
            );
          })}
        </div>

        {/* Export to Obsidian */}
        <button
          onClick={handleExportField}
          disabled={fieldExporting}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium
                     hover:bg-surface-hover transition-colors
                     text-text-secondary hover:text-accent-gold disabled:opacity-50"
          title={locale === "he" ? "ייצוא ל-Obsidian" : "Export to Obsidian"}
        >
          {fieldExporting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : fieldExported ? (
            <Check size={14} className="text-accent-green" />
          ) : (
            <Download size={14} />
          )}
          <span className="hidden sm:inline">
            {fieldExported ? "Exported!" : "Obsidian"}
          </span>
        </button>

        {/* Search toggle */}
        <button
          onClick={() => setSearchOpen((o) => !o)}
          className="p-1.5 rounded-md hover:bg-surface-hover transition-colors text-text-secondary hover:text-foreground"
          title="Search"
        >
          <Search size={16} />
        </button>

        {/* Settings placeholder */}
        <button
          className="p-1.5 rounded-md hover:bg-surface-hover transition-colors text-text-secondary hover:text-foreground"
          title="Settings"
        >
          <Settings size={16} />
        </button>
      </header>

      {/* Search bar (conditional) */}
      {searchOpen && (
        <div className="px-4 py-2 border-b border-border bg-surface shrink-0">
          <div className="flex items-center gap-2 max-w-lg">
            <Search size={14} className="text-text-tertiary flex-shrink-0" />
            <input
              autoFocus
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearchSubmit()}
              placeholder="Search this field..."
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-text-tertiary
                         focus:outline-none"
            />
            <button
              onClick={handleSearchSubmit}
              className="text-xs text-accent-gold hover:underline"
            >
              Go
            </button>
          </div>
        </div>
      )}

      {/* ---- Main 3-panel layout ---- */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Syllabus Nav */}
        <aside className="w-[280px] shrink-0 border-r border-border bg-surface overflow-hidden hidden md:block">
          <SyllabusNav field={field} onSelectConcept={setSelectedConcept} />
        </aside>

        {/* Center: Content Panel */}
        <main className="flex-1 overflow-hidden">
          <ContentPanel
            conceptId={selectedConcept}
            field={field}
            locale={locale}
            onSend={onSend}
          />
        </main>

        {/* Right: Chat panel placeholder */}
        <aside className="w-[320px] shrink-0 border-l border-border bg-surface overflow-y-auto hidden lg:flex flex-col">
          <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm p-4 text-center">
            Chat panel — send a message to start a conversation about {field}
          </div>
          <div className="p-3 border-t border-border">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Ask about this field..."
                className="flex-1 px-3 py-2 rounded-lg bg-surface-sunken border border-border
                           text-sm text-foreground placeholder:text-text-tertiary
                           focus:outline-none focus:border-accent-gold/50 transition-colors"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const target = e.target as HTMLInputElement;
                    if (target.value.trim()) {
                      onSend(target.value.trim());
                      target.value = "";
                    }
                  }
                }}
              />
            </div>
          </div>
        </aside>
      </div>

      {/* ---- Bottom: Progress Bar ---- */}
      <ProgressBar field={field} userId={userId} />
    </div>
  );
}
