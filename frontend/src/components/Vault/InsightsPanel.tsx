"use client";

import { useState } from "react";
import {
  Lightbulb,
  AlertTriangle,
  Link2,
  BookOpen,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  X,
  MessageCircle,
  Sparkles,
  Target,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface VaultAnalysis {
  analysis_id: string;
  stats: {
    notes_parsed: number;
    total_links: number;
    total_tags: number;
    total_words: number;
    avg_note_length: number;
  };
  field_detected: string | null;
  coverage_pct: number;
  mapped_concepts: number;
  unmapped_notes: number;
  gaps: {
    concept: string;
    type: string;
    paper_count: number;
    why: string;
  }[];
  hidden_connections: {
    note_a: string;
    note_b: string;
    bridge_concept: string;
    relationship: string;
    explanation: string;
  }[];
  strengths: string[];
  mappings: {
    note: string;
    concept: string;
    confidence: number;
    method: string;
  }[];
}

interface InsightsPanelProps {
  analysis: VaultAnalysis;
  onSend: (text: string) => void;
  onClose: () => void;
}

const INSIGHT_ICONS: Record<string, any> = {
  gap: Target,
  hidden_connection: Link2,
  strength: TrendingUp,
};

export default function InsightsPanel({ analysis, onSend, onClose }: InsightsPanelProps) {
  const { locale, fonts: f } = useLocaleStore();
  const [expandedSection, setExpandedSection] = useState<string | null>("overview");

  const toggle = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  const he = locale === "he";

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-accent-gold" />
          <span className="text-sm font-semibold text-foreground" style={{ fontFamily: f.display }}>
            {he ? "תובנות מהכספת" : "Vault Insights"}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-surface-hover text-text-secondary hover:text-foreground transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {/* ── Overview ── */}
        <Section
          title={he ? "סקירה כללית" : "Overview"}
          icon={<Lightbulb size={14} />}
          expanded={expandedSection === "overview"}
          onToggle={() => toggle("overview")}
        >
          <div className="grid grid-cols-2 gap-2">
            <StatCard label={he ? "פתקים" : "Notes"} value={analysis.stats.notes_parsed} />
            <StatCard label={he ? "מושגים ממופים" : "Mapped"} value={analysis.mapped_concepts} />
            <StatCard label={he ? "כיסוי" : "Coverage"} value={`${analysis.coverage_pct}%`} />
            <StatCard label={he ? "לא ממופים" : "Unmapped"} value={analysis.unmapped_notes} />
          </div>
          {analysis.field_detected && (
            <p className="text-xs text-text-secondary mt-2">
              {he ? `תחום שזוהה: ` : `Detected field: `}
              <span className="text-accent-gold font-medium">{analysis.field_detected}</span>
            </p>
          )}
          {analysis.strengths.length > 0 && (
            <div className="mt-2 space-y-1">
              {analysis.strengths.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-accent-green">
                  <TrendingUp size={12} className="mt-0.5 shrink-0" />
                  <span>{s}</span>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ── Gaps ── */}
        {analysis.gaps.length > 0 && (
          <Section
            title={he ? `פערים בידע (${analysis.gaps.length})` : `Knowledge Gaps (${analysis.gaps.length})`}
            icon={<Target size={14} className="text-accent-amber" />}
            expanded={expandedSection === "gaps"}
            onToggle={() => toggle("gaps")}
            badge={analysis.gaps.length}
          >
            <div className="space-y-2">
              {analysis.gaps.map((gap, i) => (
                <div
                  key={i}
                  className="px-3 py-2.5 rounded-lg bg-surface-sunken border-l-2 border-l-accent-amber"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground font-medium">{gap.concept}</span>
                    <span className="text-[10px] text-text-tertiary px-1.5 py-0.5 bg-surface rounded">
                      {gap.type}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary mt-1">{gap.why}</p>
                  <button
                    onClick={() => onSend(`Explain ${gap.concept} and how it connects to what I already know`)}
                    className="flex items-center gap-1 mt-2 text-[10px] text-accent-gold hover:underline"
                  >
                    <MessageCircle size={10} />
                    {he ? "שאל את קורצאק" : "Ask Korczak"}
                  </button>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Hidden Connections ── */}
        {analysis.hidden_connections.length > 0 && (
          <Section
            title={he ? `קשרים נסתרים (${analysis.hidden_connections.length})` : `Hidden Connections (${analysis.hidden_connections.length})`}
            icon={<Link2 size={14} className="text-accent-blue" />}
            expanded={expandedSection === "connections"}
            onToggle={() => toggle("connections")}
            badge={analysis.hidden_connections.length}
          >
            <div className="space-y-2">
              {analysis.hidden_connections.map((conn, i) => (
                <div
                  key={i}
                  className="px-3 py-2.5 rounded-lg bg-surface-sunken border-l-2 border-l-accent-blue"
                >
                  <div className="flex items-center gap-1.5 text-sm text-foreground font-medium flex-wrap">
                    <span>{conn.note_a}</span>
                    <Link2 size={12} className="text-accent-blue shrink-0" />
                    <span>{conn.note_b}</span>
                  </div>
                  <p className="text-xs text-text-secondary mt-1">
                    {he ? "דרך: " : "Via: "}
                    <span className="text-accent-gold">{conn.bridge_concept}</span>
                    {" — "}{conn.explanation}
                  </p>
                  <button
                    onClick={() => onSend(`Explain how ${conn.note_a} and ${conn.note_b} are connected through ${conn.bridge_concept}`)}
                    className="flex items-center gap-1 mt-2 text-[10px] text-accent-gold hover:underline"
                  >
                    <MessageCircle size={10} />
                    {he ? "העמק" : "Explore"}
                  </button>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Mappings ── */}
        {analysis.mappings.length > 0 && (
          <Section
            title={he ? `מיפוי פתקים (${analysis.mappings.length})` : `Note Mappings (${analysis.mappings.length})`}
            icon={<BookOpen size={14} />}
            expanded={expandedSection === "mappings"}
            onToggle={() => toggle("mappings")}
          >
            <div className="space-y-1">
              {analysis.mappings.map((m, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-2 py-1.5 rounded text-xs hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-text-secondary truncate">{m.note}</span>
                    <span className="text-text-tertiary shrink-0">&rarr;</span>
                    <span className="text-foreground truncate">{m.concept}</span>
                  </div>
                  <span className="text-[10px] text-text-tertiary shrink-0 ml-2">
                    {(m.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Vault stats footer */}
        <div className="text-[10px] text-text-tertiary pt-2 border-t border-border space-y-0.5">
          <p>{analysis.stats.total_words.toLocaleString()} {he ? "מילים" : "words"} | {analysis.stats.total_links} {he ? "קישורים" : "links"} | {analysis.stats.total_tags} {he ? "תגיות" : "tags"}</p>
          <p>{he ? "ממוצע" : "Avg"}: {analysis.stats.avg_note_length} {he ? "מילים לפתק" : "words/note"}</p>
        </div>
      </div>
    </div>
  );
}


// ─── Sub-components ──────────────────────────────────────────────────────────

function Section({
  title,
  icon,
  expanded,
  onToggle,
  badge,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
  badge?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left
                   hover:bg-surface-hover transition-colors"
      >
        {icon}
        <span className="text-xs font-medium text-foreground flex-1">{title}</span>
        {badge && !expanded && (
          <span className="px-1.5 py-0.5 rounded-full bg-accent-gold/10 text-accent-gold text-[10px] font-medium">
            {badge}
          </span>
        )}
        {expanded ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-1">
          {children}
        </div>
      )}
    </div>
  );
}


function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="px-3 py-2 rounded-lg bg-surface-sunken text-center">
      <p className="text-lg font-bold text-foreground">{value}</p>
      <p className="text-[10px] text-text-tertiary">{label}</p>
    </div>
  );
}
