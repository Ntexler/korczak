"use client";

import { useEffect, useState } from "react";

import { getClaimDetail, type ClaimDetail } from "@/lib/api";

import { ProvenancePanel } from "./ProvenancePanel";

interface BasicClaim {
  id: string;
  claim_text: string;
  evidence_type?: string | null;
  strength?: string | null;
  confidence?: number | null;
  claim_category?: string | null;
  verbatim_quote?: string | null;
  provenance_extracted_at?: string | null;
}

interface Props {
  claim: BasicClaim;
  isHebrew?: boolean;
  defaultExpanded?: boolean;
}

/**
 * Compact claim renderer with an expandable provenance panel.
 *
 * On expand, fetches the full claim detail from /api/claims/{id} so we get
 * the paper + authors + access info. Provenance extraction itself is a
 * separate user action inside the panel.
 */
export function ClaimCard({ claim, isHebrew = false, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded || detail) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const d = await getClaimDetail(claim.id);
        if (!cancelled) setDetail(d);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [expanded, claim.id, detail]);

  const grounded = Boolean(claim.verbatim_quote || claim.provenance_extracted_at);

  return (
    <article
      className="border border-white/10 rounded-lg bg-white/[0.02] p-3 hover:bg-white/[0.04] transition"
      dir={isHebrew ? "rtl" : "ltr"}
    >
      <p className="text-sm text-white/90 italic leading-snug">“{claim.claim_text}”</p>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {claim.evidence_type && (
          <span className="px-1.5 py-0.5 rounded bg-white/10 text-white/70">
            {claim.evidence_type}
          </span>
        )}
        {claim.strength && (
          <span
            className={`px-1.5 py-0.5 rounded ${
              claim.strength === "strong"
                ? "bg-emerald-500/15 text-emerald-300"
                : claim.strength === "moderate"
                  ? "bg-amber-500/15 text-amber-300"
                  : "bg-white/10 text-white/60"
            }`}
          >
            {claim.strength}
          </span>
        )}
        {claim.claim_category && (
          <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">
            {claim.claim_category}
          </span>
        )}
        {grounded && (
          <span
            className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300/90"
            title={isHebrew ? "ציטוט מהמקור זמין" : "Verbatim source available"}
          >
            {isHebrew ? "מעוגן" : "grounded"}
          </span>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto text-white/60 hover:text-white text-[11px] underline-offset-2 hover:underline"
        >
          {expanded
            ? isHebrew
              ? "סגור"
              : "Collapse"
            : isHebrew
              ? "מקור וציטוט"
              : "Source & quote"}
        </button>
      </div>

      {expanded && (
        <div className="mt-3">
          {loading && (
            <p className="text-xs text-white/50">
              {isHebrew ? "טוען פרטי מקור…" : "Loading source…"}
            </p>
          )}
          {error && <p className="text-xs text-red-400">{error}</p>}
          {detail && (
            <ProvenancePanel
              claim={detail}
              isHebrew={isHebrew}
              onProvenanceUpdated={(result) => {
                // Merge the fresh extraction back into the detail object so
                // subsequent re-renders don't show the stale "pending" state.
                setDetail((d) =>
                  d
                    ? {
                        ...d,
                        verbatim_quote: result.verbatim_quote,
                        quote_location: result.quote_location,
                        claim_category:
                          (result.claim_category as ClaimDetail["claim_category"]) ??
                          d.claim_category,
                        examples: result.examples,
                        provenance_sources: result.provenance_sources,
                        provenance_extracted_at: result.extracted_at,
                      }
                    : d,
                );
              }}
            />
          )}
        </div>
      )}
    </article>
  );
}
