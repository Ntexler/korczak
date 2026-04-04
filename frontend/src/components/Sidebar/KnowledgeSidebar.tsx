"use client";

import { motion } from "framer-motion";
import { X, Compass } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import GraphStats from "./GraphStats";
import TopicBrowser from "./TopicBrowser";

interface KnowledgeSidebarProps {
  onSelectTopic: (message: string) => void;
}

export default function KnowledgeSidebar({ onSelectTopic }: KnowledgeSidebarProps) {
  const { messages, sidebarOpen, setSidebarOpen } = useChatStore();

  // Extract unique concepts from conversation
  const recentConcepts: { id: string; name: string }[] = [];
  const seenIds = new Set<string>();
  for (const msg of [...messages].reverse()) {
    for (const c of msg.conceptsReferenced || []) {
      if (!seenIds.has(c.id)) {
        seenIds.add(c.id);
        recentConcepts.push(c);
      }
      if (recentConcepts.length >= 10) break;
    }
    if (recentConcepts.length >= 10) break;
  }

  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);

  if (!sidebarOpen) return null;

  return (
    <motion.aside
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.25 }}
      className="w-[280px] flex-shrink-0 border-r border-border bg-surface/50 flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Compass size={16} className="text-accent-gold" />
          <span className="text-sm font-semibold text-foreground">Explore</span>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors lg:hidden"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {/* Graph Stats */}
        <section>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Knowledge Graph
          </h3>
          <GraphStats />
        </section>

        {/* Recent Concepts from conversation */}
        {recentConcepts.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Recent Concepts
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {recentConcepts.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelectedConceptId(c.id)}
                  className="concept-badge"
                >
                  {c.name}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Topic Browser */}
        <section>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Explore Topics
          </h3>
          <TopicBrowser onSelectTopic={onSelectTopic} />
        </section>
      </div>
    </motion.aside>
  );
}
