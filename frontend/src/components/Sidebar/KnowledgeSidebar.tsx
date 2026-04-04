"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X, Compass, Search } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { searchConcepts } from "@/lib/api";
import GraphStats from "./GraphStats";
import TopicBrowser from "./TopicBrowser";

interface KnowledgeSidebarProps {
  onSelectTopic: (message: string) => void;
}

export default function KnowledgeSidebar({ onSelectTopic }: KnowledgeSidebarProps) {
  const { messages, sidebarOpen, setSidebarOpen } = useChatStore();
  const setSelectedConceptId = useChatStore((s) => s.setSelectedConceptId);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{ id: string; name: string; type: string }[]>([]);
  const [searching, setSearching] = useState(false);

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

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const results = await searchConcepts(query);
      setSearchResults(results.slice(0, 8));
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  if (!sidebarOpen) return null;

  return (
    <motion.aside
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.25 }}
      className="w-[280px] flex-shrink-0 border-r border-border bg-surface/40 flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Compass size={16} className="text-accent-gold" />
          <span className="text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-serif)" }}>
            Explore
          </span>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors lg:hidden"
        >
          <X size={16} />
        </button>
      </div>

      {/* Search */}
      <div className="px-4 pt-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search concepts..."
            className="w-full pl-9 pr-3 py-2 bg-surface-sunken border border-border-subtle rounded-lg
              text-sm text-foreground placeholder:text-text-tertiary
              focus:outline-none focus:border-accent-gold/40 focus:ring-1 focus:ring-accent-gold/15
              transition-all duration-200"
          />
        </div>
        {/* Search results */}
        {searchResults.length > 0 && (
          <div className="mt-2 space-y-0.5">
            {searchResults.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  setSelectedConceptId(c.id);
                  setSearchQuery("");
                  setSearchResults([]);
                }}
                className="flex items-center justify-between w-full px-3 py-2 rounded-lg
                  text-left text-sm text-text-secondary hover:text-foreground hover:bg-surface-hover
                  transition-colors"
              >
                <span className="truncate">{c.name}</span>
                <span className="text-[10px] text-text-tertiary ml-2">{c.type}</span>
              </button>
            ))}
          </div>
        )}
        {searching && (
          <p className="text-[10px] text-text-tertiary mt-2 px-1">Searching...</p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {/* Graph Stats */}
        <section>
          <h3 className="section-header mb-3">
            Knowledge Graph
          </h3>
          <GraphStats />
        </section>

        {/* Recent Concepts from conversation */}
        {recentConcepts.length > 0 && (
          <section>
            <h3 className="section-header mb-3">
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
          <h3 className="section-header mb-3">
            Explore Topics
          </h3>
          <TopicBrowser onSelectTopic={onSelectTopic} />
        </section>
      </div>
    </motion.aside>
  );
}
