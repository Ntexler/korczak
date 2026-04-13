"use client";

import { useRef, useEffect, useState } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";
import { sendMessage } from "@/lib/api";
import ChatMessage from "@/components/Chat/ChatMessage";
import ChatInput from "@/components/Chat/ChatInput";
import WelcomeScreen from "@/components/Welcome/WelcomeScreen";
import KnowledgeSidebar from "@/components/Sidebar/KnowledgeSidebar";
import FieldCatalog from "@/components/Home/FieldCatalog";
import FieldView from "@/components/Field/FieldView";
import { useFieldStore } from "@/stores/fieldStore";
import ConceptDetail from "@/components/ConceptPanel/ConceptDetail";
import KnowledgeGraph from "@/components/Graph/KnowledgeGraph";
import { Compass, Menu, PanelRightOpen, Languages, GraduationCap, Navigation, Radio, Map, BookOpen, TreePine, Clock, HelpCircle, Search, MoreHorizontal } from "lucide-react";
import GuidedTour from "@/components/Welcome/GuidedTour";
import GlobalSearch from "@/components/Search/GlobalSearch";
import { useLibraryStore } from "@/stores/libraryStore";
import PaperLibrary from "@/components/Library/PaperLibrary";
import KnowledgeTreeView from "@/components/Tree/KnowledgeTree";
import KnowledgeTimeline from "@/components/Timeline/KnowledgeTimeline";

export default function Home() {
  const {
    messages,
    isLoading,
    conversationId,
    mode,
    setMode,
    sidebarOpen,
    conceptPanelOpen,
    addMessage,
    setLoading,
    setConversationId,
    setSidebarOpen,
    setConceptPanelOpen,
  } = useChatStore();

  const { locale, toggleLocale, t, fonts: f, isRtl } = useLocaleStore();
  const { libraryOpen, setLibraryOpen } = useLibraryStore();
  const { currentField, setField, clearField } = useFieldStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showGraph, setShowGraph] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [showTour, setShowTour] = useState(false);

  // Check localStorage after mount (avoids SSR hydration mismatch)
  useEffect(() => {
    if (!localStorage.getItem("korczak-tour-done")) {
      setShowTour(true);
    }
  }, []);

  // TODO: Replace with actual Supabase Auth when implemented (Phase 9)
  const userId: string | undefined = "demo-researcher-1";

  const completeTour = () => {
    setShowTour(false);
    localStorage.setItem("korczak-tour-done", "1");
  };

  // Cmd+K to open search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowSearch((s) => !s);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSend = async (text: string) => {
    addMessage({ role: "user", content: text });
    setLoading(true);
    try {
      const res = await sendMessage(text, conversationId ?? undefined, mode, locale);
      if (res.conversation_id) setConversationId(res.conversation_id);
      addMessage({
        role: "assistant",
        content: res.response,
        conceptsReferenced: res.concepts_referenced,
        insight: res.insight,
      });
    } catch (err) {
      const errorText = err instanceof Error && err.message.includes("credit balance")
        ? "API credits depleted. Please add credits at console.anthropic.com to continue."
        : t.errorMessage;
      addMessage({
        role: "assistant",
        content: errorText,
      });
    } finally {
      setLoading(false);
    }
  };

  // If a field is selected, show the FieldView (new domain-first UX)
  if (currentField) {
    return (
      <div className="h-screen bg-background" dir={isRtl ? "rtl" : "ltr"} style={{ fontFamily: f.sans }}>
        <FieldView
          field={currentField}
          onBack={clearField}
          onSend={handleSend}
        />
        {/* Overlays still available */}
        {showGraph && <KnowledgeGraph onClose={() => setShowGraph(false)} />}
        {showTimeline && <KnowledgeTimeline onClose={() => setShowTimeline(false)} />}
        {showTree && userId && (
          <KnowledgeTreeView userId={userId} onClose={() => setShowTree(false)} />
        )}
        {showTour && <GuidedTour onComplete={completeTour} />}
        <GlobalSearch isOpen={showSearch} onClose={() => setShowSearch(false)} onSend={handleSend} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background" dir={isRtl ? "rtl" : "ltr"} style={{ fontFamily: f.sans }}>
      {/* Header — simplified */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface/30 backdrop-blur-sm z-10">
        {/* Left: Menu + Logo */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <Compass size={20} className="text-accent-gold" />
            <h1 className="text-lg font-bold text-foreground tracking-tight" style={{ fontFamily: f.display }}>
              {t.appName}
            </h1>
          </div>
        </div>

        {/* Center: Search bar */}
        <button
          onClick={() => setShowSearch(true)}
          className="hidden sm:flex items-center gap-2 px-4 py-1.5 rounded-xl
            bg-surface-sunken border border-border/50 text-sm text-text-tertiary
            hover:border-accent-gold/30 hover:text-text-secondary transition-all
            min-w-[280px] max-w-[400px]"
        >
          <Search size={14} />
          <span className="flex-1 text-left truncate">
            {locale === "he" ? "חפש קונספטים או שאל..." : "Search concepts or ask..."}
          </span>
          <kbd className="px-1.5 py-0.5 rounded bg-surface border border-border text-[10px]">
            {"\u2318"}K
          </kbd>
        </button>

        {/* Right: Essential controls only */}
        <div className="flex items-center gap-1.5">
          {/* Mobile search */}
          <button
            onClick={() => setShowSearch(true)}
            className="sm:hidden p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary"
          >
            <Search size={18} />
          </button>
          {/* Mode selector — compact */}
          <div className="flex items-center bg-surface-sunken rounded-full p-0.5 gap-0.5">
            {(["auto", "navigator", "tutor"] as const).map((m) => {
              const icons = { auto: Radio, navigator: Navigation, tutor: GraduationCap };
              const Icon = icons[m];
              const active = mode === m;
              return (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider transition-all
                    ${active
                      ? "bg-accent-gold-dim text-accent-gold"
                      : "text-text-tertiary hover:text-text-secondary"
                    }`}
                  title={t[m]}
                >
                  <Icon size={11} />
                  <span className="hidden lg:inline">{t[m]}</span>
                </button>
              );
            })}
          </div>
          {/* Language */}
          <button
            onClick={toggleLocale}
            className="px-2 py-1 rounded-lg text-xs hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
            title={locale === "en" ? "עברית" : "English"}
          >
            {locale === "en" ? "HE" : "EN"}
          </button>
          {/* Tools menu */}
          <div className="relative">
            <button
              onClick={() => setShowTools(!showTools)}
              className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
              title={locale === "he" ? "כלים" : "Tools"}
            >
              <MoreHorizontal size={18} />
            </button>
            {showTools && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setShowTools(false)} />
                <div className="absolute right-0 top-full mt-1 w-48 bg-surface border border-border rounded-xl shadow-xl z-30 py-1 overflow-hidden">
                  <button onClick={() => { setShowGraph(true); setShowTools(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-foreground transition-colors text-left">
                    <Map size={14} className="text-accent-gold/70" /> {t.knowledgeMap}
                  </button>
                  {userId && (
                    <button onClick={() => { setShowTree(true); setShowTools(false); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-foreground transition-colors text-left">
                      <TreePine size={14} className="text-accent-gold/70" /> {t.knowledgeTree}
                    </button>
                  )}
                  <button onClick={() => { setShowTimeline(true); setShowTools(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-foreground transition-colors text-left">
                    <Clock size={14} className="text-accent-gold/70" /> {locale === "he" ? "ציר זמן" : "Timeline"}
                  </button>
                  <button onClick={() => { setLibraryOpen(!libraryOpen); setShowTools(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-foreground transition-colors text-left">
                    <BookOpen size={14} className="text-accent-gold/70" /> {t.library}
                  </button>
                  <div className="border-t border-border my-1" />
                  <button onClick={() => { setShowTour(true); setShowTools(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-foreground transition-colors text-left">
                    <HelpCircle size={14} className="text-text-tertiary" /> {locale === "he" ? "סיור מודרך" : "Guided Tour"}
                  </button>
                </div>
              </>
            )}
          </div>
          {/* Panel toggle */}
          <button
            onClick={() => setConceptPanelOpen(!conceptPanelOpen)}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <PanelRightOpen size={18} />
          </button>
        </div>
      </header>

      {/* Main content — 3-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Library panel (replaces sidebar when active) */}
        {libraryOpen && userId ? (
          <PaperLibrary userId={userId} onClose={() => setLibraryOpen(false)} />
        ) : (
          /* Left sidebar */
          <KnowledgeSidebar onSelectTopic={handleSend} />
        )}

        {/* Center — Chat */}
        <main className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
            {messages.length === 0 ? (
              <div className="max-w-[900px] mx-auto">
                <FieldCatalog onSelectField={setField} />
              </div>
            ) : (
              <div className="max-w-[760px] mx-auto">
                {messages.map((msg) => (
                  <ChatMessage
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    conceptsReferenced={msg.conceptsReferenced}
                    insight={msg.insight}
                    onSend={handleSend}
                  />
                ))}
                {isLoading && (
                  <div className="flex justify-start mb-4">
                    <div className="flex gap-3 items-start">
                      <div className="w-8 h-8 rounded-full bg-accent-gold-dim flex items-center justify-center mt-1">
                        <Compass size={16} className="text-accent-gold" />
                      </div>
                      <div className="bg-surface rounded-2xl px-4 py-3 rounded-bl-sm flex items-center gap-3">
                        <span className="thinking-text">{t.navigating}</span>
                        <div className="flex gap-1.5">
                          <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-1" />
                          <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-2" />
                          <span className="w-1.5 h-1.5 bg-accent-gold/60 rounded-full dot-bounce-3" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <ChatInput onSend={handleSend} disabled={isLoading} />
        </main>

        {/* Right panel — Concept Detail */}
        <ConceptDetail researcherId={userId} />
      </div>

      {/* Knowledge Graph overlay */}
      {showGraph && <KnowledgeGraph onClose={() => setShowGraph(false)} />}

      {/* Knowledge Timeline overlay */}
      {showTimeline && <KnowledgeTimeline onClose={() => setShowTimeline(false)} />}

      {/* Knowledge Tree overlay */}
      {showTree && userId && (
        <KnowledgeTreeView userId={userId} onClose={() => setShowTree(false)} />
      )}

      {/* Guided Tour */}
      {showTour && <GuidedTour onComplete={completeTour} />}

      {/* Global Search */}
      <GlobalSearch isOpen={showSearch} onClose={() => setShowSearch(false)} onSend={handleSend} />
    </div>
  );
}
