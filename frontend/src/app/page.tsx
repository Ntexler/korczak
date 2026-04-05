"use client";

import { useRef, useEffect, useState } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useLocaleStore } from "@/stores/localeStore";
import { sendMessage } from "@/lib/api";
import ChatMessage from "@/components/Chat/ChatMessage";
import ChatInput from "@/components/Chat/ChatInput";
import WelcomeScreen from "@/components/Welcome/WelcomeScreen";
import KnowledgeSidebar from "@/components/Sidebar/KnowledgeSidebar";
import ConceptDetail from "@/components/ConceptPanel/ConceptDetail";
import KnowledgeGraph from "@/components/Graph/KnowledgeGraph";
import { Compass, Menu, PanelRightOpen, Languages, GraduationCap, Navigation, Radio, Map } from "lucide-react";

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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showGraph, setShowGraph] = useState(false);

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

  return (
    <div className="flex flex-col h-screen bg-background" dir={isRtl ? "rtl" : "ltr"} style={{ fontFamily: f.sans }}>
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface/30 backdrop-blur-sm z-10">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <Compass size={20} className="text-accent-gold" />
            <h1
              className="text-lg font-bold text-foreground tracking-tight"
              style={{ fontFamily: f.display }}
            >
              {t.appName}
            </h1>
            <span className="hidden sm:inline text-text-secondary text-sm">
              {t.subtitle}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Language toggle */}
          <button
            onClick={toggleLocale}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs
              hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
            title={locale === "en" ? "עברית" : "English"}
          >
            <Languages size={14} />
            <span className="font-medium">{locale === "en" ? "HE" : "EN"}</span>
          </button>
          {/* Knowledge Map button */}
          <button
            onClick={() => setShowGraph(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs
              hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
            title={t.knowledgeMap}
          >
            <Map size={14} />
            <span className="hidden sm:inline font-medium">{t.knowledgeMap}</span>
          </button>
          {/* Mode selector */}
          <div className="flex items-center bg-surface-sunken rounded-full p-0.5 gap-0.5">
            {(["auto", "navigator", "tutor"] as const).map((m) => {
              const icons = { auto: Radio, navigator: Navigation, tutor: GraduationCap };
              const Icon = icons[m];
              const active = mode === m;
              return (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider transition-all
                    ${active
                      ? "bg-accent-gold-dim text-accent-gold"
                      : "text-text-tertiary hover:text-text-secondary"
                    }`}
                  title={t[m]}
                >
                  <Icon size={11} />
                  <span className="hidden sm:inline">{t[m]}</span>
                </button>
              );
            })}
          </div>
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
        {/* Left sidebar */}
        <KnowledgeSidebar onSelectTopic={handleSend} />

        {/* Center — Chat */}
        <main className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
            {messages.length === 0 ? (
              <WelcomeScreen onSend={handleSend} />
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
        <ConceptDetail />
      </div>

      {/* Knowledge Graph overlay */}
      {showGraph && <KnowledgeGraph onClose={() => setShowGraph(false)} />}
    </div>
  );
}
