"use client";

import { Hash } from "lucide-react";
import { Section } from "@/stores/readingStore";
import { useLocaleStore } from "@/stores/localeStore";

interface SectionNavProps {
  sections: Section[];
  onJumpTo: (offset: number) => void;
}

export default function SectionNav({ sections, onJumpTo }: SectionNavProps) {
  const { t } = useLocaleStore();

  if (sections.length === 0) return null;

  return (
    <aside className="w-[200px] border-r border-border overflow-y-auto py-4 px-3 hidden md:block">
      <h4 className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-3 px-1">
        {t.sections}
      </h4>
      <nav className="space-y-0.5">
        {sections.map((section, i) => (
          <button
            key={i}
            onClick={() => onJumpTo(section.offset)}
            className="w-full flex items-start gap-2 px-2 py-1.5 rounded-lg text-left
              hover:bg-surface-hover transition-colors group"
          >
            <Hash size={10} className="text-text-tertiary mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-xs text-foreground group-hover:text-accent-gold transition-colors">
                {section.section}
              </span>
              {section.concepts.length > 0 && (
                <div className="flex flex-wrap gap-0.5 mt-1">
                  {section.concepts.slice(0, 3).map((c) => (
                    <span
                      key={c.id}
                      className="px-1 py-0.5 rounded bg-accent-gold/10 text-accent-gold text-[8px]"
                    >
                      {c.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </button>
        ))}
      </nav>
    </aside>
  );
}
