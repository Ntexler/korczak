"use client";

import { useEffect, useState } from "react";
import { BookOpen, ArrowDown, ArrowUp, FileText, Link2 } from "lucide-react";
import ConceptTooltip from "./ConceptTooltip";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Paper {
  id: string;
  title: string;
  year?: number;
}

interface Connection {
  id: string;
  name: string;
  relationship?: string;
}

interface ConceptData {
  id: string;
  name: string;
  definition?: string;
  explanation?: string;
  key_papers?: Paper[];
  connections?: Connection[];
  description?: string;
}

interface FieldOverview {
  name: string;
  description?: string;
  paper_count?: number;
  concept_count?: number;
  top_concepts?: { id: string; name: string }[];
}

interface ContentPanelProps {
  conceptId: string | null;
  field: string;
  locale: string;
  onSend: (text: string) => void;
}

/** Replace concept names in text with clickable ConceptTooltip components. */
function renderTextWithConcepts(
  text: string,
  concepts: { id: string; name: string }[],
  onSelect: (id: string) => void
): React.ReactNode[] {
  if (!concepts.length) return [text];

  // Sort by name length desc so longer names are matched first
  const sorted = [...concepts].sort((a, b) => b.name.length - a.name.length);
  const pattern = sorted
    .map((c) => c.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const regex = new RegExp(`(${pattern})`, "gi");
  const parts = text.split(regex);

  return parts.map((part, i) => {
    const match = sorted.find(
      (c) => c.name.toLowerCase() === part.toLowerCase()
    );
    if (match) {
      return (
        <ConceptTooltip
          key={`${match.id}-${i}`}
          conceptId={match.id}
          name={part}
          onSelect={onSelect}
        />
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function ContentPanel({
  conceptId,
  field,
  locale,
  onSend,
}: ContentPanelProps) {
  const [concept, setConcept] = useState<ConceptData | null>(null);
  const [overview, setOverview] = useState<FieldOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState<string | null>(conceptId);

  // Sync external conceptId prop
  useEffect(() => {
    setSelectedConcept(conceptId);
  }, [conceptId]);

  // Fetch concept detail
  useEffect(() => {
    if (!selectedConcept) {
      setConcept(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/features/explain/${encodeURIComponent(selectedConcept)}?locale=${locale}`
        );
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const data = await res.json();
        if (!cancelled) setConcept(data);
      } catch {
        if (!cancelled) setConcept(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedConcept, locale]);

  // Fetch field overview when no concept
  useEffect(() => {
    if (selectedConcept) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/features/fields/${encodeURIComponent(field)}`
        );
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setOverview(data);
        }
      } catch {
        // non-critical
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [field, selectedConcept]);

  const handleSelectConcept = (id: string) => {
    setSelectedConcept(id);
  };

  // All known concepts for inline linking
  const allConcepts: { id: string; name: string }[] = [
    ...(concept?.connections?.map((c) => ({ id: c.id, name: c.name })) ?? []),
    ...(overview?.top_concepts ?? []),
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        Loading...
      </div>
    );
  }

  // --- Field overview (no concept selected) ---
  if (!selectedConcept) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <h2 className="text-2xl font-bold text-foreground mb-2">{field}</h2>
        {overview?.description && (
          <p className="text-text-secondary text-sm mb-6 leading-relaxed">
            {overview.description}
          </p>
        )}

        {/* Stats */}
        <div className="flex gap-6 mb-8">
          {overview?.paper_count != null && (
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {overview.paper_count}
              </span>
              <span className="text-xs text-text-tertiary">papers</span>
            </div>
          )}
          {overview?.concept_count != null && (
            <div className="text-center">
              <span className="block text-lg font-semibold text-foreground">
                {overview.concept_count}
              </span>
              <span className="text-xs text-text-tertiary">concepts</span>
            </div>
          )}
        </div>

        {/* Top concepts */}
        {overview?.top_concepts && overview.top_concepts.length > 0 && (
          <div>
            <h3 className="section-header mb-3">Top Concepts</h3>
            <div className="flex flex-wrap gap-2">
              {overview.top_concepts.map((c) => (
                <ConceptTooltip
                  key={c.id}
                  conceptId={c.id}
                  name={c.name}
                  onSelect={handleSelectConcept}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // --- Concept detail ---
  if (!concept) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        Concept not found
      </div>
    );
  }

  const explanationText =
    concept.explanation || concept.definition || concept.description || "";

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Concept name */}
      <h2 className="text-2xl font-bold text-foreground mb-4">{concept.name}</h2>

      {/* Explanation */}
      {explanationText && (
        <div className="text-text-secondary text-sm leading-relaxed mb-6">
          {renderTextWithConcepts(explanationText, allConcepts, handleSelectConcept)}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mb-8">
        <button
          onClick={() => onSend(`Explain "${concept.name}" in simpler terms`)}
          className="follow-up-chip flex items-center gap-1.5"
        >
          <ArrowDown size={12} />
          Explain simpler
        </button>
        <button
          onClick={() => onSend(`Go deeper on "${concept.name}"`)}
          className="follow-up-chip flex items-center gap-1.5"
        >
          <ArrowUp size={12} />
          Go deeper
        </button>
      </div>

      {/* Key papers */}
      {concept.key_papers && concept.key_papers.length > 0 && (
        <div className="mb-6">
          <h3 className="section-header mb-3 flex items-center gap-1.5">
            <FileText size={12} /> Key Papers
          </h3>
          <ul className="space-y-2">
            {concept.key_papers.map((paper) => (
              <li
                key={paper.id}
                className="flex items-start gap-2 text-sm text-text-secondary"
              >
                <BookOpen size={12} className="mt-1 flex-shrink-0 text-text-tertiary" />
                <span>
                  {paper.title}
                  {paper.year && (
                    <span className="text-text-tertiary ml-1">({paper.year})</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Connections */}
      {concept.connections && concept.connections.length > 0 && (
        <div>
          <h3 className="section-header mb-3 flex items-center gap-1.5">
            <Link2 size={12} /> Connections
          </h3>
          <div className="flex flex-wrap gap-2">
            {concept.connections.map((conn) => (
              <ConceptTooltip
                key={conn.id}
                conceptId={conn.id}
                name={conn.name}
                onSelect={handleSelectConcept}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
