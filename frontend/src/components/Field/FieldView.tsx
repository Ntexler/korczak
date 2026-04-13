"use client";

import { useState, useRef, useEffect } from "react";
import {
  ArrowLeft,
  Search,
  Settings,
  GraduationCap,
  FlaskConical,
  Compass as CompassIcon,
  Send,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useFieldStore } from "@/stores/fieldStore";
import { useChatStore } from "@/stores/chatStore";
import { sendMessage } from "@/lib/api";
import ChatMessage from "@/components/Chat/ChatMessage";
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
  discover: { label: "Discover", icon: CompassIcon },
} as const;

type FieldMode = "learn" | "research" | "discover";

export default function FieldView({ field, onBack, onSend }: FieldViewProps) {
  const { fonts: f, locale } = useLocaleStore();
  const { currentMode, setMode } = useFieldStore();
  const { messages, isLoading, conversationId, addMessage, setLoading, setConversationId } = useChatStore();
  const [selectedConcept, setSelectedConcept] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [chatInput, setChatInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  const userId = "demo-researcher-1";

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

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

  const handleSearchSubmit = () => {
    if (searchQuery.trim()) {
      handleChatSend(searchQuery.trim());
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
            onSend={handleSendFromContent}
          />
        </main>

        {/* Right: Live Chat */}
        <aside className="w-[320px] shrink-0 border-l border-border bg-surface hidden lg:flex flex-col">
          {/* Chat header */}
          <div className="px-3 py-2 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">
            {locale === "he" ? "צ'אט — " : "Chat — "}{field}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full text-text-tertiary text-xs text-center px-4">
                {locale === "he"
                  ? `שאל שאלה על ${field}, או לחץ "תסביר עוד" בתוכן`
                  : `Ask about ${field}, or click "Explain more" in content`
                }
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
          <div className="p-3 border-t border-border">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={locale === "he" ? "שאל על התחום..." : "Ask about this field..."}
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
                onClick={() => { if (chatInput.trim()) { handleChatSend(chatInput.trim()); setChatInput(""); }}}
                className="p-2 rounded-lg bg-accent-gold text-background hover:bg-accent-gold/90 transition-colors"
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </aside>
      </div>

      {/* ---- Bottom: Progress Bar ---- */}
      <ProgressBar field={field} userId={userId} />
    </div>
  );
}
