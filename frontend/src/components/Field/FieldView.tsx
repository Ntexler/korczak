"use client";

import { useState, useRef, useEffect } from "react";
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
  ChevronDown,
  Send,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useFieldStore } from "@/stores/fieldStore";
import { useChatStore } from "@/stores/chatStore";
import { exportFieldToObsidian, exportAnkiDeck, sendMessage } from "@/lib/api";
import ChatMessage from "@/components/Chat/ChatMessage";
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
  const { messages, isLoading, conversationId, addMessage, setLoading, setConversationId } = useChatStore();
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [selectedConceptName, setSelectedConceptName] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [fieldExporting, setFieldExporting] = useState(false);
  const [fieldExported, setFieldExported] = useState(false);
  const [ankiExporting, setAnkiExporting] = useState(false);
  const [ankiExported, setAnkiExported] = useState(false);
  const [rightPanel, setRightPanel] = useState<RightPanel>("chat");
  const [vaultAnalysis, setVaultAnalysis] = useState<any>(null);
  const [leftView, setLeftView] = useState<"graph" | "list">(currentMode === "learn" ? "list" : "graph");
  const [fieldSwitcherOpen, setFieldSwitcherOpen] = useState(false);
  const [fieldSearch, setFieldSearch] = useState("");
  const [availableFields, setAvailableFields] = useState<{ name: string; paper_count: number }[]>([]);
  // Live chat state (merged in from main)
  const [chatInput, setChatInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedConcept) {
        setSelectedConcept(null);
        setSelectedConceptName(null);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [selectedConcept]);

  // Fetch available fields for switcher
  useEffect(() => {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    fetch(`${API_BASE}/features/fields`)
      .then((res) => res.ok ? res.json() : { fields: [] })
      .then((data) => setAvailableFields(data.fields || []))
      .catch(() => {});
  }, []);

  // Auto-scroll the chat pane to the newest message (from main)
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const userId = "mock-user";
  const he = locale === "he";

  const handleChatSend = async (text: string) => {
    const prefixedText = `[${field}] ${text}`;
    addMessage({ role: "user", content: text });
    setLoading(true);
    try {
      const res = await sendMessage(prefixedText, conversationId ?? undefined, "navigator", locale);
      if (res.conversation_id) setConversationId(res.conversation_id);
      addMessage({
        role: "assistant",
        content: res.response,
        conceptsReferenced: res.concepts_referenced,
        insight: res.insight,
      });
    } catch {
      addMessage({ role: "assistant", content: "An error occurred. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  const handleSendFromContent = (text: string) => {
    handleChatSend(text);
  };

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
      handleChatSend(searchQuery.trim());
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

        {/* Field switcher + concept breadcrumb */}
        <div className="flex items-center gap-1.5 min-w-0 relative">
          <button
            onClick={() => setFieldSwitcherOpen((o) => !o)}
            className="flex items-center gap-1 text-base font-semibold text-foreground hover:text-accent-gold transition-colors truncate"
            style={{ fontFamily: f.display }}
          >
            {field}
            <ChevronDown size={14} className="text-text-tertiary shrink-0" />
          </button>
          {selectedConcept && selectedConceptName && (
            <>
              <span className="text-text-tertiary text-sm shrink-0">/</span>
              <span className="text-sm text-accent-gold truncate max-w-[200px]">
                {selectedConceptName}
              </span>
            </>
          )}

          {/* Field switcher dropdown */}
          {fieldSwitcherOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setFieldSwitcherOpen(false)} />
              <div className="absolute top-full left-0 mt-1 w-64 max-h-80 overflow-y-auto
                              bg-surface border border-border rounded-lg shadow-xl z-50">
                <div className="p-2">
                  <input
                    autoFocus
                    type="text"
                    value={fieldSearch}
                    onChange={(e) => setFieldSearch(e.target.value)}
                    placeholder={he ? "חפש תחום..." : "Search field..."}
                    className="w-full px-3 py-1.5 rounded bg-surface-sunken border border-border
                               text-sm text-foreground placeholder:text-text-tertiary
                               focus:outline-none focus:border-accent-gold/50 mb-1"
                  />
                </div>
                <div className="px-1 pb-1">
                  {availableFields
                    .filter((af) => af.name.toLowerCase().includes(fieldSearch.toLowerCase()))
                    .map((af) => (
                      <button
                        key={af.name}
                        onClick={() => {
                          setFieldSwitcherOpen(false);
                          setFieldSearch("");
                          if (af.name !== field) {
                            onBack();
                          }
                        }}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded text-left text-sm transition-colors ${
                          af.name === field
                            ? "bg-accent-gold/10 text-accent-gold"
                            : "text-foreground hover:bg-surface-hover"
                        }`}
                      >
                        <span className="truncate">{af.name}</span>
                        {af.paper_count > 0 && (
                          <span className="text-[10px] text-text-tertiary shrink-0 ml-2">
                            {af.paper_count} papers
                          </span>
                        )}
                      </button>
                    ))}
                </div>
              </div>
            </>
          )}
        </div>

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
              {currentMode === "learn"
                ? (leftView === "graph" ? (he ? "גרף ידע" : "Knowledge Graph") : (he ? "מסלול למידה" : "Learning Path"))
                : currentMode === "research"
                  ? (he ? "גרף מחקר" : "Research Graph")
                  : (he ? "חקירה חופשית" : "Free Exploration")}
            </span>
            {currentMode === "learn" && (
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
            )}
          </div>
          {/* Content — mode-dependent */}
          <div className="flex-1 overflow-hidden">
            {currentMode === "learn" ? (
              /* Learn: syllabus list by default, graph toggle available */
              leftView === "graph" ? (
                <ConceptGraph field={field} onSelectConcept={setSelectedConcept} selectedConceptId={selectedConcept} />
              ) : (
                <SyllabusNav field={field} onSelectConcept={setSelectedConcept} />
              )
            ) : currentMode === "research" ? (
              /* Research: always graph — connections matter */
              <ConceptGraph field={field} onSelectConcept={setSelectedConcept} selectedConceptId={selectedConcept} />
            ) : (
              /* Discover: always graph — free exploration */
              <ConceptGraph field={field} onSelectConcept={setSelectedConcept} selectedConceptId={selectedConcept} />
            )}
          </div>
        </aside>

        {/* Center: Content Panel */}
        <main className="flex-1 overflow-hidden">
          <ContentPanel
            conceptId={selectedConcept}
            field={field}
            locale={locale}
            onSend={handleSendFromContent}
            onConceptLoaded={setSelectedConceptName}
          />
        </main>

        {/* Right panel — dynamic: insights / vault / live chat */}
        <aside className="w-[320px] shrink-0 border-l border-border bg-surface overflow-hidden hidden lg:flex flex-col">
          {rightPanel === "insights" && vaultAnalysis ? (
            <InsightsPanel
              analysis={vaultAnalysis}
              onSend={handleChatSend}
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
            /* Default: Live chat (merged in from main) */
            <>
              {/* Chat header */}
              <div className="px-3 py-2 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider shrink-0">
                {he ? "צ'אט — " : "Chat — "}{field}
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
                {messages.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-text-tertiary text-xs text-center px-4">
                    <div className="space-y-3">
                      <MessageCircle size={28} className="mx-auto text-text-tertiary/40" />
                      <p>
                        {he
                          ? `שאל שאלה על ${field}, או לחץ "תסביר עוד" בתוכן`
                          : `Ask about ${field}, or click "Explain more" in content`}
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    {messages.map((msg) => (
                      <ChatMessage
                        key={msg.id}
                        role={msg.role}
                        content={msg.content}
                        conceptsReferenced={msg.conceptsReferenced}
                        insight={msg.insight}
                        onSend={handleChatSend}
                      />
                    ))}
                    {isLoading && (
                      <div className="flex gap-1.5 py-2">
                        <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-1" />
                        <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-2" />
                        <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-3" />
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </>
                )}
              </div>

              {/* Input */}
              <div className="p-3 border-t border-border shrink-0">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder={he ? "שאל על התחום..." : "Ask about this field..."}
                    className="flex-1 px-3 py-2 rounded-lg bg-surface-sunken border border-border
                               text-sm text-foreground placeholder:text-text-tertiary
                               focus:outline-none focus:border-accent-gold/50 transition-colors"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && chatInput.trim()) {
                        handleChatSend(chatInput.trim());
                        setChatInput("");
                      }
                    }}
                  />
                  <button
                    onClick={() => {
                      if (chatInput.trim()) {
                        handleChatSend(chatInput.trim());
                        setChatInput("");
                      }
                    }}
                    className="p-2 rounded-lg bg-accent-gold text-background hover:bg-accent-gold/90 transition-colors"
                    aria-label={he ? "שלח" : "Send"}
                  >
                    <Send size={14} />
                  </button>
                </div>
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
