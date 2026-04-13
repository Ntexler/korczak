"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, BookOpen, FileText, ArrowRight } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface FieldInfo {
  name: string;
  paper_count: number;
  course_count: number;
  description?: string;
}

interface FieldCatalogProps {
  onSelectField: (field: string) => void;
}

export default function FieldCatalog({ onSelectField }: FieldCatalogProps) {
  const { fonts: f } = useLocaleStore();
  const [fields, setFields] = useState<FieldInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/features/fields`);
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const data: FieldInfo[] = await res.json();
        if (!cancelled) setFields(data);
      } catch {
        // Fallback: show empty state
        if (!cancelled) setFields([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    const visible = fields
      .filter((f) => f.paper_count > 0)
      .sort((a, b) => b.paper_count - a.paper_count);
    if (!search.trim()) return visible;
    const q = search.toLowerCase();
    return visible.filter((f) => f.name.toLowerCase().includes(q));
  }, [fields, search]);

  return (
    <div className="flex flex-col h-full px-6 py-8 overflow-y-auto">
      {/* Header */}
      <div className="text-center mb-8">
        <h1
          className="text-3xl font-bold text-foreground mb-2"
          style={{ fontFamily: f.display }}
        >
          Explore Fields
        </h1>
        <p className="text-text-secondary text-sm">
          Choose a field of knowledge to explore
        </p>
      </div>

      {/* Search */}
      <div className="max-w-xl mx-auto w-full mb-6">
        <div className="relative">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter fields..."
            className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-surface border border-border
                       text-foreground text-sm placeholder:text-text-tertiary
                       focus:outline-none focus:border-accent-gold/50 transition-colors"
          />
        </div>
      </div>

      {/* Search across all fields option */}
      <div className="max-w-4xl mx-auto w-full mb-6">
        <button
          onClick={() => onSelectField("__all__")}
          className="w-full flex items-center justify-between px-4 py-3 rounded-lg
                     bg-surface border border-border hover:border-accent-gold/40
                     text-text-secondary hover:text-foreground transition-all group"
        >
          <span className="flex items-center gap-2 text-sm">
            <Search size={14} className="text-accent-gold" />
            Search across all fields
          </span>
          <ArrowRight
            size={14}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-accent-gold"
          />
        </button>
      </div>

      {/* Field cards grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-text-tertiary text-sm">
          Loading fields...
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center py-20 text-text-tertiary text-sm">
          No fields found
        </div>
      ) : (
        <div className="max-w-4xl mx-auto w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((field) => (
            <button
              key={field.name}
              onClick={() => onSelectField(field.name)}
              className="exhibit-card text-left group cursor-pointer"
            >
              <h3
                className="text-foreground font-semibold mb-2 group-hover:text-accent-gold transition-colors"
                style={{ fontFamily: f.display }}
              >
                {field.name}
              </h3>
              {field.description && (
                <p className="text-text-secondary text-xs mb-3 line-clamp-2">
                  {field.description}
                </p>
              )}
              <div className="flex items-center gap-4 text-xs text-text-tertiary">
                <span className="flex items-center gap-1">
                  <FileText size={12} />
                  {field.paper_count} papers
                </span>
                <span className="flex items-center gap-1">
                  <BookOpen size={12} />
                  {field.course_count} courses
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
