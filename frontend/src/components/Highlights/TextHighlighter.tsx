"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Highlighter, MessageSquare, Plus } from "lucide-react";
import { useHighlightStore } from "@/stores/highlightStore";
import { useLocaleStore } from "@/stores/localeStore";
import { createHighlight } from "@/lib/api";

interface TextHighlighterProps {
  children: React.ReactNode;
  sourceType: string;
  sourceId: string;
  userId?: string;
}

const HIGHLIGHT_COLORS = ["#E8B931", "#58A6FF", "#3FB950", "#BC8CFF", "#F78166"];

export default function TextHighlighter({
  children,
  sourceType,
  sourceId,
  userId,
}: TextHighlighterProps) {
  const { isHighlightMode, selectedColor, addHighlight } = useHighlightStore();
  const { t } = useLocaleStore();
  const [showToolbar, setShowToolbar] = useState(false);
  const [toolbarPos, setToolbarPos] = useState({ x: 0, y: 0 });
  const [selectedText, setSelectedText] = useState("");
  const [annotation, setAnnotation] = useState("");
  const [showAnnotation, setShowAnnotation] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseUp = useCallback(() => {
    if (!isHighlightMode || !userId) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      setShowToolbar(false);
      return;
    }

    const text = selection.toString().trim();
    if (text.length < 3) return;

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const containerRect = containerRef.current?.getBoundingClientRect();

    if (containerRect) {
      setToolbarPos({
        x: rect.left - containerRect.left + rect.width / 2,
        y: rect.top - containerRect.top - 8,
      });
    }

    setSelectedText(text);
    setShowToolbar(true);
    setShowAnnotation(false);
    setAnnotation("");
  }, [isHighlightMode, userId]);

  const handleHighlight = async () => {
    if (!userId || !selectedText) return;
    try {
      const result = await createHighlight({
        user_id: userId,
        source_type: sourceType,
        source_id: sourceId,
        highlighted_text: selectedText,
        annotation: annotation || undefined,
        color: selectedColor,
      });
      if (result.id) {
        addHighlight(result);
      }
    } catch {
      // Silently fail
    }
    setShowToolbar(false);
    window.getSelection()?.removeAllRanges();
  };

  return (
    <div ref={containerRef} className="relative" onMouseUp={handleMouseUp}>
      {children}

      {/* Floating toolbar */}
      <AnimatePresence>
        {showToolbar && (
          <motion.div
            initial={{ opacity: 0, y: 4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.95 }}
            className="absolute z-50 bg-surface border border-border-subtle rounded-xl shadow-lg px-2 py-1.5"
            style={{
              left: `${toolbarPos.x}px`,
              top: `${toolbarPos.y}px`,
              transform: "translate(-50%, -100%)",
            }}
          >
            {showAnnotation ? (
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={annotation}
                  onChange={(e) => setAnnotation(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleHighlight()}
                  placeholder={t.annotate}
                  className="bg-surface-sunken text-xs text-foreground px-2 py-1 rounded-lg
                    placeholder:text-text-tertiary focus:outline-none w-[160px]"
                  autoFocus
                />
                <button
                  onClick={handleHighlight}
                  className="p-1 rounded-lg bg-accent-gold/20 text-accent-gold hover:bg-accent-gold/30"
                >
                  <Plus size={12} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                {/* Color options */}
                {HIGHLIGHT_COLORS.map((c) => (
                  <button
                    key={c}
                    onClick={() => {
                      useHighlightStore.getState().setSelectedColor(c);
                      handleHighlight();
                    }}
                    className="w-5 h-5 rounded-full transition-transform hover:scale-110"
                    style={{ backgroundColor: c, opacity: 0.8 }}
                  />
                ))}
                <div className="w-px h-4 bg-border mx-1" />
                <button
                  onClick={() => setShowAnnotation(true)}
                  className="p-1 rounded-lg text-text-tertiary hover:text-foreground"
                  title={t.annotate}
                >
                  <MessageSquare size={13} />
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
