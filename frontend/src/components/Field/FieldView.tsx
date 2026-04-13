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
  FileArchive,
  MessageCircle,
  Brain,
  List,
  GitFork,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useFieldStore } from "@/stores/fieldStore";
import { exportFieldToObsidian, exportAnkiDeck } from "@/lib/api";
import SyllabusNav from "./SyllabusNav";
import ContentPanel from "./ContentPanel";
import ConceptGraph from "./ConceptGraph";
import ProgressBar from "./ProgressBar";
import VaultUpload from "@/components/Vault/VaultUpload";
import InsightsPanel from "@/components/Vault/InsightsPanel";

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
type RightPanel = "chat" | "vault" | "insights";

export default function FieldView({ field, onBack, onSend }: FieldViewProps) {
  const { fonts: f, locale } = useLocaleStore();
  const { currentMode, setMode } = useFieldStore();
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [fieldExporting, setFieldExporting] = useState(false);
  const [fieldExported, setFieldExported] = useState(false);
  const [ankiExporting, setAnkiExporting] = useState(false);
  const [ankiExported, setAnkiExported] = useState(false);
  const [rightPanel, setRightPanel] = useState<RightPanel>("chat");
  const [vaultAnalysis, setVaultAnalysis] = useState<any>(null);
  const [leftView, setLeftView] = useState<"graph" | "list">("graph");

  const userId = "mock-user";
  const he = locale === "he";

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

  const handleExportAnki = async () => {
    if (ankiExporting) return;
    setAnkiExporting(true);
    try {
      const blob = await exportAnkiDeck(field, undefined, locale);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeName = field.replace(/\s+/g, "_").replace(/&/g, "and");
      a.download = `Korczak_${safeName}_anki.txt`;
      a.click();
      URL.revokeObjectURL(url);
      setAnkiExported(true);
      setTimeout(() => setAnkiExported(false), 3000);
    } catch (e) {
      console.error("Anki export failed:", e);
    } finally {
      setAnkiExporting(false);
    }
  };

  const handleSearchSubmit = () => {
    if (searchQuery.trim()) {
      onSend(searchQuery.trim());
      setSearchQuery("");
      setSearchOpen(false);
    }
  };

  const handleVaultAnalysisComplete = (result: any) => {
    setVaultAnalysis(result);
    setRightPanel("insights");
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ---- Header ---- */}
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-surface shrink-0">
        <button
          onClick={onBack}
          className="p-1.5 rounded-md hover:bg-surface-hover transition-colors text-text-secondary hover:text-foreground"
          title="Back"
        >
          <ArrowLeft size={18} />
        </button>

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
          title={he ? "ייצוא ל-Obsidian" : "Export to Obsidian"}
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

        {/* Anki export */}
        <button
          onClick={handleExportAnki}
          disabled={ankiExporting}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium
                     hover:bg-surface-hover transition-colors
                     text-text-secondary hover:text-accent-gold disabled:opacity-50"
          title={he ? "ייצוא ל-Anki" : "Export to Anki"}
        >
          {ankiExporting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : ankiExported ? (
            <Check size={14} className="text-accent-green" />
          ) : (
            <Brain size={14} />
          )}
          <span className="hidden sm:inline">
            {ankiExported ? "Exported!" : "Anki"}
          </span>
        </button>

        {/* Import Vault toggle */}
        <button
          onClick={() => setRightPanel(rightPanel === "vault" ? "chat" : "vault")}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium
                     transition-colors
                     ${rightPanel === "vault" || rightPanel === "insights"
                       ? "bg-accent-gold/10 text-accent-gold"
                       : "text-text-secondary hover:text-accent-gold hover:bg-surface-hover"
                     }`}
          title={he ? "ייבוא כספת" : "Import Vault"}
        >
          <FileArchive size={14} />
          <span className="hidden sm:inline">
            {he ? "כספת" : "Vault"}
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

        <button
          className="p-1.5 rounded-md hover:bg-surface-hover transition-colors text-text-secondary hover:text-foreground"
          title="Settings"
        >
          <Settings size={16} />
        </button>
      </header>

      {/* Search bar */}
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
        {/* Left: Graph or Syllabus Nav */}
        <aside className={`${leftView === "graph" ? "w-[400px]" : "w-[280px]"} shrink-0 border-r border-border bg-surface overflow-hidden hidden md:flex flex-col transition-all`}>
          {/* View toggle */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
            <span className="text-[10px] text-text-tertiary uppercase tracking-wider">
              {leftView === "graph" ? (he ? "גרף ידע" : "Knowledge Graph") : (he ? "סילבוס" : "Syllabus")}
            </span>
            <div className="flex items-center rounded border border-border bg-surface-sunken">
              <button
                onClick={() => setLeftView("graph")}
                className={`p-1.5 transition-colors ${leftView === "graph" ? "text-accent-gold bg-accent-gold/10" : "text-text-tertiary hover:text-text-secondary"}`}
                title={he ? "גרף" : "Graph"}
              >
                <GitFork size={13} />
              </button>
              <button
                onClick={() => setLeftView("list")}
                className={`p-1.5 transition-colors ${leftView === "list" ? "text-accent-gold bg-accent-gold/10" : "text-text-tertiary hover:text-text-secondary"}`}
                title={he ? "רשימה" : "List"}
              >
                <List size={13} />
              </button>
            </div>
          </div>
          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {leftView === "graph" ? (
              <ConceptGraph
                field={field}
                onSelectConcept={setSelectedConcept}
                selectedConceptId={selectedConcept}
              />
            ) : (
              <SyllabusNav field={field} onSelectConcept={setSelectedConcept} />
            )}
          </div>
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

        {/* Right panel — dynamic */}
        <aside className="w-[320px] shrink-0 border-l border-border bg-surface overflow-hidden hidden lg:flex flex-col">
          {rightPanel === "insights" && vaultAnalysis ? (
            <InsightsPanel
              analysis={vaultAnalysis}
              onSend={onSend}
              onClose={() => setRightPanel("chat")}
            />
          ) : rightPanel === "vault" ? (
            <div className="flex flex-col h-full">
              <div className="px-4 py-3 border-b border-border shrink-0">
                <h3 className="text-sm font-semibold text-foreground" style={{ fontFamily: f.display }}>
                  {he ? "ייבוא כספת Obsidian" : "Import Obsidian Vault"}
                </h3>
                <p className="text-[10px] text-text-tertiary mt-0.5">
                  {he ? "שתף את הכספת שלך כדי שקורצאק ילמד מה אתה יודע" : "Share your vault so Korczak learns what you know"}
                </p>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                <VaultUpload
                  field={field}
                  onAnalysisComplete={handleVaultAnalysisComplete}
                />
              </div>
            </div>
          ) : (
            /* Default: Chat panel */
            <>
              <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm p-4 text-center">
                <div className="space-y-3">
                  <MessageCircle size={28} className="mx-auto text-text-tertiary/40" />
                  <p>{he ? "שלח הודעה כדי להתחיל שיחה" : `Chat about ${field}`}</p>
                </div>
              </div>
              <div className="p-3 border-t border-border">
                <input
                  type="text"
                  placeholder={he ? "שאל על התחום..." : "Ask about this field..."}
                  className="w-full px-3 py-2 rounded-lg bg-surface-sunken border border-border
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
            </>
          )}
        </aside>
      </div>

      {/* ---- Bottom: Progress Bar ---- */}
      <ProgressBar field={field} userId={userId} />
    </div>
  );
}
