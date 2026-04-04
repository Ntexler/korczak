"use client";

import { BookOpen } from "lucide-react";

const TOPICS = [
  "Anthropological Theory",
  "Indigenous & Decolonial Studies",
  "Environmental Anthropology",
  "Political Anthropology",
  "Medical & Health Anthropology",
  "Cultural & Symbolic Anthropology",
  "Critical & Postcolonial Anthropology",
  "Economic Anthropology",
  "Digital & Technology Studies",
  "Historical Anthropology",
  "Language & Communication",
  "Religion, Ritual & Ethics",
  "Urban & Spatial Anthropology",
  "Methods & Methodology",
  "Migration & Humanitarianism",
  "Sleep & Cognition Research",
];

interface TopicBrowserProps {
  onSelectTopic: (topic: string) => void;
}

export default function TopicBrowser({ onSelectTopic }: TopicBrowserProps) {
  return (
    <div className="space-y-1">
      {TOPICS.map((topic) => (
        <button
          key={topic}
          onClick={() => onSelectTopic(`Tell me about ${topic}`)}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-left text-sm
            text-text-secondary hover:text-foreground hover:bg-surface-hover
            transition-all duration-150 group"
        >
          <BookOpen
            size={13}
            className="text-accent-gold/50 group-hover:text-accent-gold transition-colors flex-shrink-0"
          />
          <span className="truncate">{topic}</span>
        </button>
      ))}
    </div>
  );
}
