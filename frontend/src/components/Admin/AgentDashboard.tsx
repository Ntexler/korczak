"use client";

import { useEffect, useState } from "react";
import {
  Bot, CheckCircle, XCircle, Clock, Globe, Link2, Users,
  ChevronDown, ChevronUp, Search, Send, Plus, ExternalLink,
  AlertTriangle, TrendingUp, Eye,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Enrichment {
  id: string;
  concept_name: string;
  field: string;
  enrichment_type: string;
  source: string;
  content: string;
  references: any[];
  question_asked: string;
  status: string;
  priority: number;
  created_at: string;
  reviewed_by?: string;
  review_note?: string;
}

interface AgentStats {
  pending: number;
  approved: number;
  rejected: number;
}

interface Expert {
  id: string;
  name: string;
  field: string;
  contact_type: string;
  contact_id: string;
  status: string;
}

type Tab = "activity" | "review" | "sources" | "experts";

export default function AgentDashboard() {
  const { locale, fonts: f } = useLocaleStore();
  const he = locale === "he";
  const [tab, setTab] = useState<Tab>("review");
  const [enrichments, setEnrichments] = useState<Enrichment[]>([]);
  const [stats, setStats] = useState<AgentStats>({ pending: 0, approved: 0, rejected: 0 });
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [manualUrl, setManualUrl] = useState("");
  const [manualField, setManualField] = useState("Anthropology");

  // Fetch enrichments
  useEffect(() => {
    (async () => {
      try {
        const [enrichRes, statsRes] = await Promise.all([
          fetch(`${API_BASE}/admin/enrichments?limit=50`),
          fetch(`${API_BASE}/admin/enrichments/stats`),
        ]);
        if (enrichRes.ok) setEnrichments(await enrichRes.json().then(d => d.enrichments || []));
        if (statsRes.ok) setStats(await statsRes.json());
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  const handleApprove = async (id: string) => {
    try {
      await fetch(`${API_BASE}/admin/enrichments/${id}/approve`, { method: "POST" });
      setEnrichments(prev => prev.map(e => e.id === id ? { ...e, status: "approved" } : e));
      setStats(prev => ({ ...prev, pending: prev.pending - 1, approved: prev.approved + 1 }));
    } catch { /* ignore */ }
  };

  const handleReject = async (id: string) => {
    try {
      await fetch(`${API_BASE}/admin/enrichments/${id}/reject`, { method: "POST" });
      setEnrichments(prev => prev.map(e => e.id === id ? { ...e, status: "rejected" } : e));
      setStats(prev => ({ ...prev, pending: prev.pending - 1, rejected: prev.rejected + 1 }));
    } catch { /* ignore */ }
  };

  const handleAddUrl = async () => {
    if (!manualUrl.trim()) return;
    try {
      await fetch(`${API_BASE}/admin/sources/url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: manualUrl, field: manualField }),
      });
      setManualUrl("");
    } catch { /* ignore */ }
  };

  const TYPE_COLORS: Record<string, string> = {
    definition: "text-blue-400 bg-blue-500/10",
    claim: "text-green-400 bg-green-500/10",
    connection: "text-purple-400 bg-purple-500/10",
    source: "text-amber-400 bg-amber-500/10",
    confidence_update: "text-red-400 bg-red-500/10",
  };

  const SOURCE_ICONS: Record<string, string> = {
    scibot: "🤖",
    multi_search: "🔍",
    manual: "✍️",
    expert: "🎓",
    reddit: "💬",
  };

  const pendingEnrichments = enrichments.filter(e => e.status === "pending");
  const recentActivity = enrichments.filter(e => e.status !== "pending").slice(0, 20);

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-surface shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-accent-gold/10 flex items-center justify-center">
              <Bot size={20} className="text-accent-gold" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground" style={{ fontFamily: f.display }}>
                {he ? "סוכן הלמידה" : "Learning Agent"}
              </h1>
              <p className="text-xs text-text-tertiary">
                {he ? "ניהול, אישור, ומקורות" : "Monitor, approve, and manage sources"}
              </p>
            </div>
          </div>
          {/* Stats */}
          <div className="flex gap-4">
            <div className="text-center">
              <p className="text-lg font-bold text-amber-400">{stats.pending}</p>
              <p className="text-[10px] text-text-tertiary">{he ? "ממתין" : "Pending"}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-green-400">{stats.approved}</p>
              <p className="text-[10px] text-text-tertiary">{he ? "אושר" : "Approved"}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-red-400">{stats.rejected}</p>
              <p className="text-[10px] text-text-tertiary">{he ? "נדחה" : "Rejected"}</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-4">
          {([
            { key: "review" as Tab, label: he ? "אישורים" : "Review", icon: CheckCircle, count: stats.pending },
            { key: "activity" as Tab, label: he ? "פעילות" : "Activity", icon: TrendingUp },
            { key: "sources" as Tab, label: he ? "מקורות" : "Sources", icon: Globe },
            { key: "experts" as Tab, label: he ? "מומחים" : "Experts", icon: Users },
          ]).map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                tab === t.key
                  ? "bg-accent-gold/10 text-accent-gold"
                  : "text-text-tertiary hover:text-text-secondary hover:bg-surface-hover"
              }`}
            >
              <t.icon size={13} />
              {t.label}
              {t.count ? (
                <span className="px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 text-[10px]">
                  {t.count}
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ── Review Tab ── */}
        {tab === "review" && (
          <div className="space-y-3">
            {pendingEnrichments.length === 0 ? (
              <div className="text-center py-12 text-text-tertiary">
                <CheckCircle size={32} className="mx-auto mb-3 text-green-400/40" />
                <p className="text-sm">{he ? "אין פריטים ממתינים לאישור" : "No items pending review"}</p>
              </div>
            ) : (
              pendingEnrichments.map(e => (
                <EnrichmentCard
                  key={e.id}
                  enrichment={e}
                  expanded={expandedId === e.id}
                  onToggle={() => setExpandedId(expandedId === e.id ? null : e.id)}
                  onApprove={() => handleApprove(e.id)}
                  onReject={() => handleReject(e.id)}
                  typeColors={TYPE_COLORS}
                  sourceIcons={SOURCE_ICONS}
                  he={he}
                />
              ))
            )}
          </div>
        )}

        {/* ── Activity Tab ── */}
        {tab === "activity" && (
          <div className="space-y-2">
            {recentActivity.map(e => (
              <div key={e.id} className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-surface border border-border/50">
                <span className="text-sm">{SOURCE_ICONS[e.source] || "📄"}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate">{e.concept_name}</p>
                  <p className="text-[10px] text-text-tertiary">{e.enrichment_type} — {e.field}</p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded ${
                  e.status === "approved" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"
                }`}>
                  {e.status}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ── Sources Tab ── */}
        {tab === "sources" && (
          <div className="space-y-6">
            {/* Add URL manually */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3">
                {he ? "הוסף מקור ידנית" : "Add Source Manually"}
              </h3>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualUrl}
                  onChange={(e) => setManualUrl(e.target.value)}
                  placeholder={he ? "הכנס כתובת URL..." : "Enter URL..."}
                  className="flex-1 px-3 py-2 rounded-lg bg-surface-sunken border border-border
                             text-sm text-foreground placeholder:text-text-tertiary
                             focus:outline-none focus:border-accent-gold/50"
                />
                <select
                  value={manualField}
                  onChange={(e) => setManualField(e.target.value)}
                  className="px-3 py-2 rounded-lg bg-surface-sunken border border-border
                             text-sm text-foreground"
                >
                  <option value="Anthropology">Anthropology</option>
                  <option value="Medicine">Medicine</option>
                  <option value="Psychology">Psychology</option>
                  <option value="Economics">Economics</option>
                  <option value="Philosophy">Philosophy</option>
                  <option value="Computer Science">Computer Science</option>
                </select>
                <button
                  onClick={handleAddUrl}
                  className="px-4 py-2 rounded-lg bg-accent-gold text-background text-sm font-medium
                             hover:bg-accent-gold/90 transition-colors"
                >
                  <Plus size={16} />
                </button>
              </div>
            </div>

            {/* Active sources */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3">
                {he ? "מקורות פעילים" : "Active Sources"}
              </h3>
              <div className="space-y-2">
                {[
                  { name: "OpenAlex", type: "API", status: "active", papers: "250M+" },
                  { name: "Semantic Scholar", type: "API", status: "active", papers: "200M+" },
                  { name: "CrossRef", type: "API", status: "active", papers: "140M+" },
                  { name: "Europe PMC", type: "API", status: "active", papers: "40M+" },
                  { name: "CORE", type: "API", status: "active", papers: "200M+" },
                  { name: "Sci-Bot", type: "Web", status: "limited", papers: "88M (to 2021)" },
                  { name: "MIT OCW", type: "Scraper", status: "active", papers: "Syllabi" },
                  { name: "Open Syllabus", type: "API", status: "active", papers: "Rankings" },
                  { name: "SciCrunch", type: "API", status: "active", papers: "500K RRIDs" },
                ].map(src => (
                  <div key={src.name} className="flex items-center justify-between px-4 py-2.5 rounded-lg bg-surface border border-border/50">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${
                        src.status === "active" ? "bg-green-400" : "bg-amber-400"
                      }`} />
                      <span className="text-sm text-foreground">{src.name}</span>
                      <span className="text-[10px] text-text-tertiary px-1.5 py-0.5 bg-surface-sunken rounded">{src.type}</span>
                    </div>
                    <span className="text-[10px] text-text-tertiary">{src.papers}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Experts Tab ── */}
        {tab === "experts" && (
          <div className="space-y-6">
            <div className="bg-accent-gold/5 border border-accent-gold/20 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-foreground mb-2">
                {he ? "חבר מומחה" : "Connect an Expert"}
              </h3>
              <p className="text-xs text-text-secondary mb-4">
                {he
                  ? "חבר פרופסור או מומחה לתחום ספציפי. קורצאק ישאל אותו שאלות ממוקדות ויבין מהתשובות."
                  : "Connect a professor or domain expert. Korczak will ask them targeted questions and learn from their answers."}
              </p>
              <div className="grid grid-cols-2 gap-3">
                <input
                  placeholder={he ? "שם המומחה" : "Expert name"}
                  className="px-3 py-2 rounded-lg bg-surface-sunken border border-border text-sm text-foreground
                             placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold/50"
                />
                <input
                  placeholder={he ? "תחום" : "Field"}
                  className="px-3 py-2 rounded-lg bg-surface-sunken border border-border text-sm text-foreground
                             placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold/50"
                />
                <select
                  className="px-3 py-2 rounded-lg bg-surface-sunken border border-border text-sm text-foreground"
                >
                  <option value="whatsapp">WhatsApp</option>
                  <option value="email">Email</option>
                  <option value="telegram">Telegram</option>
                </select>
                <input
                  placeholder={he ? "מספר / כתובת" : "Number / Address"}
                  className="px-3 py-2 rounded-lg bg-surface-sunken border border-border text-sm text-foreground
                             placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold/50"
                />
              </div>
              <button className="mt-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-gold text-background text-sm font-medium
                                 hover:bg-accent-gold/90 transition-colors">
                <Users size={14} />
                {he ? "חבר מומחה" : "Connect Expert"}
              </button>
            </div>

            <div className="text-center py-8 text-text-tertiary">
              <Users size={32} className="mx-auto mb-3 text-text-tertiary/30" />
              <p className="text-sm">{he ? "אין מומחים מחוברים עדיין" : "No experts connected yet"}</p>
              <p className="text-xs text-text-tertiary mt-1">
                {he ? "חבר מומחה ראשון כדי שקורצאק יוכל לשאול שאלות" : "Connect your first expert so Korczak can ask questions"}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function EnrichmentCard({
  enrichment: e,
  expanded,
  onToggle,
  onApprove,
  onReject,
  typeColors,
  sourceIcons,
  he,
}: {
  enrichment: Enrichment;
  expanded: boolean;
  onToggle: () => void;
  onApprove: () => void;
  onReject: () => void;
  typeColors: Record<string, string>;
  sourceIcons: Record<string, string>;
  he: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-hover transition-colors"
      >
        <span className="text-lg">{sourceIcons[e.source] || "📄"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{e.concept_name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${typeColors[e.enrichment_type] || "text-text-tertiary bg-surface-sunken"}`}>
              {e.enrichment_type}
            </span>
          </div>
          <p className="text-[10px] text-text-tertiary mt-0.5">
            {e.field} — {e.source} — {new Date(e.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {e.priority > 10 && <AlertTriangle size={12} className="text-amber-400" />}
          {expanded ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border/30 space-y-3">
          {/* Question asked */}
          {e.question_asked && (
            <div className="mt-3">
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">
                {he ? "שאלה ששאל" : "Question asked"}
              </p>
              <p className="text-xs text-text-secondary italic">{e.question_asked}</p>
            </div>
          )}

          {/* Content */}
          <div>
            <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">
              {he ? "תוכן מוצע" : "Proposed content"}
            </p>
            <div className="text-sm text-foreground bg-surface-sunken rounded-lg p-3 leading-relaxed max-h-40 overflow-y-auto">
              {e.content}
            </div>
          </div>

          {/* References */}
          {e.references && e.references.length > 0 && (
            <div>
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">
                {he ? "מקורות" : "References"} ({e.references.length})
              </p>
              <div className="space-y-1">
                {e.references.slice(0, 5).map((ref: any, i: number) => (
                  <div key={i} className="text-xs text-text-secondary flex items-start gap-1">
                    <span className="text-text-tertiary shrink-0">{i + 1}.</span>
                    <span>{ref.title || ref.url || ref.doi || "Unknown"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={onApprove}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                         bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
            >
              <CheckCircle size={14} />
              {he ? "אשר" : "Approve"}
            </button>
            <button
              onClick={onReject}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                         bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
            >
              <XCircle size={14} />
              {he ? "דחה" : "Reject"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
