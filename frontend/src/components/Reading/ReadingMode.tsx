"use client";

import { useEffect, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { X, Clock, BookOpen } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { useReadingStore } from "@/stores/readingStore";
import { startReadingSession, updateReadingSession, endReadingSession, getPaperSections } from "@/lib/api";
import SectionNav from "./SectionNav";
import ReadingTimer from "./ReadingTimer";

interface ReadingModeProps {
  paperId: string;
  paperTitle: string;
  userId?: string;
  onClose: () => void;
}

export default function ReadingMode({ paperId, paperTitle, userId, onClose }: ReadingModeProps) {
  const { t } = useLocaleStore();
  const {
    activeSession, sectionMap, readingTime,
    setActiveSession, setSectionMap, setReadingTime, incrementReadingTime,
  } = useReadingStore();
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Start session and load sections
  useEffect(() => {
    loadSections();
    if (userId) startSession();

    // Timer: increment every second
    timerRef.current = setInterval(() => {
      incrementReadingTime();
    }, 1000);

    // Heartbeat: send progress every 30 seconds
    heartbeatRef.current = setInterval(() => {
      sendHeartbeat();
    }, 30000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      if (userId && activeSession) {
        endReadingSession(activeSession.id).catch(() => {});
      }
    };
  }, [paperId]);

  const loadSections = async () => {
    try {
      const res = await getPaperSections(paperId);
      setSectionMap(res.sections || []);
    } catch {
      setSectionMap([]);
    }
  };

  const startSession = async () => {
    if (!userId) return;
    try {
      const res = await startReadingSession(userId, paperId);
      setActiveSession(res);
      setReadingTime(0);
    } catch {
      // Continue without session tracking
    }
  };

  const sendHeartbeat = async () => {
    const session = useReadingStore.getState().activeSession;
    const time = useReadingStore.getState().readingTime;
    if (!session) return;
    try {
      const scrollDepth = contentRef.current
        ? contentRef.current.scrollTop / (contentRef.current.scrollHeight - contentRef.current.clientHeight)
        : 0;
      await updateReadingSession(session.id, {
        total_seconds: time,
        scroll_depth: Math.min(1, Math.max(0, scrollDepth)),
      });
    } catch {
      // Silently fail
    }
  };

  const handleClose = async () => {
    if (activeSession) {
      try {
        await endReadingSession(activeSession.id);
      } catch {
        // Continue
      }
    }
    setActiveSession(null);
    setReadingTime(0);
    onClose();
  };

  const scrollToSection = useCallback((offset: number) => {
    // Find the section element by data attribute or estimate position
    if (contentRef.current) {
      const totalHeight = contentRef.current.scrollHeight;
      const totalText = sectionMap.reduce((acc, s) => acc + s.text.length, 0);
      const ratio = totalText > 0 ? offset / totalText : 0;
      contentRef.current.scrollTo({
        top: ratio * totalHeight,
        behavior: "smooth",
      });
    }
  }, [sectionMap]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 bg-background flex flex-col"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface/30 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <BookOpen size={18} className="text-accent-gold" />
          <div>
            <h2 className="text-sm font-semibold text-foreground line-clamp-1">{paperTitle}</h2>
            <span className="text-[10px] text-text-tertiary uppercase tracking-wider">{t.readingMode}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <ReadingTimer seconds={readingTime} />
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Section nav sidebar */}
        <SectionNav sections={sectionMap} onJumpTo={scrollToSection} />

        {/* Paper content */}
        <div
          ref={contentRef}
          className="flex-1 overflow-y-auto px-8 py-6 max-w-[800px] mx-auto"
        >
          {sectionMap.length === 0 ? (
            <div className="text-center py-12 text-text-tertiary">
              <BookOpen size={32} className="mx-auto mb-3 opacity-40" />
              <p className="text-sm">{t.noSections}</p>
            </div>
          ) : (
            sectionMap.map((section, i) => (
              <div key={i} className="mb-8" data-section-offset={section.offset}>
                <h3 className="text-xs font-semibold text-accent-gold uppercase tracking-wider mb-3">
                  {section.section}
                </h3>
                {/* Concept tags */}
                {section.concepts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {section.concepts.map((c) => (
                      <span
                        key={c.id}
                        className="concept-badge text-[10px]"
                      >
                        {c.name}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                  {section.text}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </motion.div>
  );
}
