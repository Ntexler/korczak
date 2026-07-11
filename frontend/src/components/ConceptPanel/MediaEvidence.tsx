"use client";

import { useEffect, useState } from "react";
import { Film, Sparkles, Plus, Quote, Eye, Loader2 } from "lucide-react";
import {
  getConceptMedia,
  discoverConceptMedia,
  contributeMedia,
  type MediaEvidenceItem,
} from "@/lib/api";
import { useLocaleStore } from "@/stores/localeStore";

const STATUS_STYLE: Record<string, { label_en: string; label_he: string; cls: string }> = {
  grounded: { label_en: "grounded in transcript", label_he: "מעוגן בתמלול", cls: "text-accent-green" },
  contested: { label_en: "contested reading", label_he: "קריאה שנויה במחלוקת", cls: "text-accent-amber" },
  refuted: { label_en: "not grounded", label_he: "לא מעוגן", cls: "text-accent-red" },
  unverified: { label_en: "Korczak's reading", label_he: "פרשנות של קורצ'אק", cls: "text-text-tertiary" },
};

export default function MediaEvidence({ conceptId }: { conceptId: string }) {
  const { locale } = useLocaleStore();
  const he = locale === "he";
  const [items, setItems] = useState<MediaEvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [showContribute, setShowContribute] = useState(false);
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getConceptMedia(conceptId)
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [conceptId]);

  const handleDiscover = async () => {
    if (discovering) return;
    setDiscovering(true);
    setError(null);
    try {
      const found = await discoverConceptMedia(conceptId);
      if (found.length) setItems(found);
    } catch {
      setError(he ? "החיפוש נכשל — נסה שוב" : "Discovery failed — try again");
    } finally {
      setDiscovering(false);
    }
  };

  const handleContribute = async () => {
    if (!url.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await contributeMedia(conceptId, url.trim(), note.trim() || undefined);
      setUrl("");
      setNote("");
      setShowContribute(false);
      const refreshed = await getConceptMedia(conceptId);
      setItems(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h3 className="section-header flex items-center gap-2">
          <Film size={12} />
          {he ? "מדיה כעדות" : "Media as evidence"}
        </h3>
        <button
          onClick={() => setShowContribute((s) => !s)}
          className="text-[10px] text-text-tertiary hover:text-accent-gold flex items-center gap-1 transition-colors"
          title={he ? "הצבע על קטע שממחיש טענה" : "Point at a clip that illustrates a claim"}
        >
          <Plus size={11} />
          {he ? "תרום קטע" : "Contribute"}
        </button>
      </div>

      {/* Contribute — the lecturer/researcher path */}
      {showContribute && (
        <div className="mb-3 p-3 rounded-lg bg-surface-sunken space-y-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={he ? "קישור YouTube / archive.org" : "YouTube / archive.org link"}
            className="w-full px-2 py-1.5 text-xs rounded bg-surface border border-border text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold"
            dir="ltr"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={he ? "למה הקטע הזה חשוב? (לא חובה)" : "Why does this clip matter? (optional)"}
            className="w-full px-2 py-1.5 text-xs rounded bg-surface border border-border text-foreground placeholder:text-text-tertiary focus:outline-none focus:border-accent-gold"
          />
          <button
            onClick={handleContribute}
            disabled={submitting || !url.trim()}
            className="w-full py-1.5 text-xs rounded bg-accent-gold-dim text-accent-gold hover:bg-accent-gold/20 disabled:opacity-40 transition-colors flex items-center justify-center gap-1.5"
          >
            {submitting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {he ? "פרש ושמור" : "Interpret & save"}
          </button>
        </div>
      )}

      {error && <p className="text-[10px] text-accent-red mb-2">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-2 text-text-tertiary text-xs py-3">
          <Loader2 size={12} className="animate-spin" />
          {he ? "טוען מדיה…" : "Loading media…"}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-4">
          <p className="text-[11px] text-text-tertiary mb-3">
            {he
              ? "אין עדיין מדיה למושג הזה. שנביא רגעים מכוננים ונפרש אותם?"
              : "No media yet for this concept. Bring founding moments and read them?"}
          </p>
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="mx-auto px-3 py-1.5 text-xs rounded bg-accent-gold-dim text-accent-gold hover:bg-accent-gold/20 disabled:opacity-40 transition-colors flex items-center gap-1.5"
          >
            {discovering ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {he ? "הַעֲמֵק — הבא מדיה" : "Deepen — bring media"}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((m) => (
            <MediaCard key={m.id} item={m} he={he} />
          ))}
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="w-full py-1.5 text-[11px] rounded text-text-tertiary hover:text-accent-gold hover:bg-surface-hover disabled:opacity-40 transition-colors flex items-center justify-center gap-1.5"
          >
            {discovering ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {he ? "הבא עוד" : "Bring more"}
          </button>
        </div>
      )}
    </section>
  );
}

function MediaCard({ item, he }: { item: MediaEvidenceItem; he: boolean }) {
  const status = STATUS_STYLE[item.consensus_status] || STATUS_STYLE.unverified;
  const isImage = item.media_kind === "image";

  return (
    <div className="rounded-lg overflow-hidden bg-surface-sunken border border-border">
      {/* The embed — everything happens in front of the eyes, no link-out */}
      <div className="relative w-full bg-black" style={{ aspectRatio: "16 / 9" }}>
        {isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.embed_url}
            alt={item.title || ""}
            className="w-full h-full object-contain"
          />
        ) : (
          <iframe
            src={item.embed_url}
            title={item.title || "media"}
            allow="accelerometer; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
            loading="lazy"
            className="w-full h-full border-0"
          />
        )}
      </div>

      <div className="p-3 space-y-2">
        {item.title && (
          <p className="text-xs font-medium text-foreground leading-snug line-clamp-2">
            {item.title}
          </p>
        )}

        {/* Korczak's reading — the meaning, marked as interpretation */}
        {item.interpretation && (
          <p className="text-[11px] text-text-secondary leading-relaxed">
            {item.interpretation}
          </p>
        )}

        {/* Between the lines — subtext, always with its basis */}
        {item.subtext && (
          <div className="pl-2 border-l-2 border-l-accent-amber/50">
            <p className="text-[11px] text-accent-amber/90 leading-relaxed flex items-start gap-1">
              <Eye size={11} className="mt-0.5 flex-shrink-0" />
              <span>
                <span className="font-medium">{he ? "בין השורות: " : "Between the lines: "}</span>
                {item.subtext}
              </span>
            </p>
            {item.subtext_basis && (
              <p className="text-[10px] text-text-tertiary italic mt-1">
                {he ? "בסיס: " : "basis: "}
                {item.subtext_basis}
              </p>
            )}
          </div>
        )}

        {/* Grounding quote — what was actually said */}
        {item.grounding_quote && (
          <p className="text-[10px] text-text-tertiary italic flex items-start gap-1 leading-relaxed">
            <Quote size={10} className="mt-0.5 flex-shrink-0" />
            &ldquo;{item.grounding_quote}&rdquo;
          </p>
        )}

        <div className="flex items-center justify-between pt-1">
          <span className={`text-[9px] uppercase tracking-wide ${status.cls}`}>
            {he ? status.label_he : status.label_en}
          </span>
          <span className="text-[9px] text-text-tertiary">
            {item.source.replace("_", " ")}
            {item.brought_by === "contributor" && (he ? " · תרומה" : " · contributed")}
          </span>
        </div>
      </div>
    </div>
  );
}
