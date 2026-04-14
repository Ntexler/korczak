"use client";

import { useState } from "react";

import type { ClaimDetail, ProvenanceResponse } from "@/lib/api";
import { extractClaimProvenance } from "@/lib/api";

import { AccessBadge } from "./AccessBadge";
import { AuthorProfileDrawer } from "./AuthorProfileDrawer";

interface Props {
  claim: ClaimDetail;
  isHebrew?: boolean;
  onProvenanceUpdated?: (result: ProvenanceResponse) => void;
}

const CATEGORY_LABEL: Record<string, { en: string; he: string; className: string }> = {
  main: { en: "Main finding", he: "ממצא מרכזי", className: "bg-emerald-500/20 text-emerald-300" },
  supporting: { en: "Supporting evidence", he: "עדות תומכת", className: "bg-sky-500/20 text-sky-300" },
  background: { en: "Background (prior work)", he: "רקע (מספרות קיימת)", className: "bg-white/10 text-white/70" },
  limitation: { en: "Limitation", he: "מגבלה", className: "bg-amber-500/20 text-amber-300" },
};

/**
 * Expanded provenance view for a single claim.
 *
 * Surfaces:
 *  - claim category
 *  - verbatim quote + source (if extracted)
 *  - "Extract original passage" button that triggers multi-source extraction
 *    on first use and is cached for subsequent viewers
 *  - examples
 *  - source paper metadata: title, year, authors (clickable → drawer), access
 *  - funding list
 *  - provenance_sources list (which sources were checked)
 */
export function ProvenancePanel({ claim, isHebrew = false, onProvenanceUpdated }: Props) {
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<ProvenanceResponse | null>(null);
  const [activeAuthorOpenalex, setActiveAuthorOpenalex] = useState<string | null>(null);

  const verbatim = fresh?.verbatim_quote ?? claim.verbatim_quote;
  const location = fresh?.quote_location ?? claim.quote_location;
  const category = fresh?.claim_category ?? claim.claim_category;
  const examples = fresh?.examples ?? claim.examples ?? [];
  const sources = fresh?.provenance_sources ?? claim.provenance_sources ?? [];
  const extractedAt = fresh?.extracted_at ?? claim.provenance_extracted_at;

  const canExtract = Boolean(
    (claim.paper?.id && (claim.paper?.doi || claim.paper?.access_url)) || verbatim
  );

  async function runExtract(force = false) {
    if (extracting) return;
    setExtracting(true);
    setExtractError(null);
    try {
      const result = await extractClaimProvenance(claim.id, force);
      setFresh(result);
      onProvenanceUpdated?.(result);
    } catch (e) {
      setExtractError(String(e));
    } finally {
      setExtracting(false);
    }
  }

  const authors = claim.paper?.authors || [];
  const categoryLabel = category && CATEGORY_LABEL[category];

  return (
    <div className="mt-3 space-y-4 text-sm text-white/85" dir={isHebrew ? "rtl" : "ltr"}>
      {/* Category chip */}
      {categoryLabel && (
        <div>
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${categoryLabel.className}`}>
            {isHebrew ? categoryLabel.he : categoryLabel.en}
          </span>
        </div>
      )}

      {/* Verbatim quote */}
      <section>
        <div className="flex items-center justify-between mb-1">
          <h5 className="text-xs uppercase tracking-wider text-white/50">
            {isHebrew ? "ציטוט מקורי" : "Original passage"}
          </h5>
          {extractedAt && (
            <span className="text-[10px] text-white/40">
              {isHebrew ? "מקור חולץ" : "extracted"} {new Date(extractedAt).toLocaleDateString()}
            </span>
          )}
        </div>
        {verbatim ? (
          <blockquote className="border-l-2 border-emerald-500/40 pl-3 text-white/90 italic leading-relaxed">
            “{verbatim}”
            {location && (
              <footer className="mt-1 not-italic text-xs text-white/50">— {location}</footer>
            )}
          </blockquote>
        ) : (
          <div className="rounded border border-dashed border-white/10 p-3 text-white/60 bg-white/[0.02]">
            <p className="mb-2">
              {isHebrew
                ? "טרם חולץ ציטוט מקורי לטענה הזו."
                : "No original passage extracted yet."}
            </p>
            <button
              type="button"
              onClick={() => runExtract(false)}
              disabled={!canExtract || extracting}
              className="rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1 text-xs font-medium transition"
            >
              {extracting
                ? isHebrew
                  ? "מחלץ…"
                  : "Extracting…"
                : isHebrew
                  ? "חלץ מהמקור ומקורות חלופיים"
                  : "Extract from source + alt sources"}
            </button>
            {!canExtract && (
              <p className="mt-2 text-[11px] text-white/40">
                {isHebrew
                  ? "אין DOI או גישה למאמר — חילוץ לא זמין."
                  : "No DOI or access URL on paper — extraction unavailable."}
              </p>
            )}
          </div>
        )}
        {extractError && (
          <p className="mt-2 text-xs text-red-400">{extractError}</p>
        )}
      </section>

      {/* Examples */}
      {examples.length > 0 && (
        <section>
          <h5 className="text-xs uppercase tracking-wider text-white/50 mb-1">
            {isHebrew ? "דוגמאות מהמאמר" : "Examples from the paper"}
          </h5>
          <ul className="space-y-2">
            {examples.map((ex, idx) => (
              <li key={idx} className="bg-white/[0.03] border border-white/5 rounded p-2">
                <p className="text-white/85">{ex.text}</p>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-white/50">
                  {ex.kind && <span className="uppercase">{ex.kind}</span>}
                  {ex.location && <span>· {ex.location}</span>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Source paper metadata */}
      {claim.paper && (
        <section className="border-t border-white/5 pt-3">
          <h5 className="text-xs uppercase tracking-wider text-white/50 mb-1">
            {isHebrew ? "מאמר המקור" : "Source paper"}
          </h5>
          <p className="text-white/90 font-medium leading-snug">
            {claim.paper.title || "(untitled)"}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-white/55">
            {claim.paper.publication_year && <span>{claim.paper.publication_year}</span>}
            {authors.length > 0 && <span>·</span>}
            {authors.slice(0, 3).map((a, i) => (
              <button
                key={`${a.name}-${i}`}
                type="button"
                onClick={() => a.openalex_id && setActiveAuthorOpenalex(a.openalex_id)}
                className={`text-white/70 ${a.openalex_id ? "hover:text-emerald-300 hover:underline" : "cursor-default"}`}
                disabled={!a.openalex_id}
                title={a.bio || a.institution || ""}
              >
                {a.name}
                {a.country ? ` (${a.country})` : ""}
                {i < Math.min(authors.length, 3) - 1 ? "," : ""}
              </button>
            ))}
            {authors.length > 3 && <span>{isHebrew ? `ועוד ${authors.length - 3}` : `+${authors.length - 3} more`}</span>}
          </div>
          <div className="mt-2">
            <AccessBadge paper={claim.paper} />
          </div>
        </section>
      )}

      {/* Funding */}
      {claim.paper?.funding && claim.paper.funding.length > 0 && (
        <section>
          <h5 className="text-xs uppercase tracking-wider text-white/50 mb-1">
            {isHebrew ? "מימון" : "Funding"}
          </h5>
          <ul className="flex flex-wrap gap-1">
            {claim.paper.funding.map((f, idx) => (
              <li
                key={idx}
                className="text-[11px] bg-white/5 border border-white/10 rounded-full px-2 py-0.5 text-white/70"
                title={f.grant_id || undefined}
              >
                {f.funder || f.funder_id || "(unknown funder)"}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Provenance sources breakdown */}
      {sources.length > 0 && (
        <details className="text-xs text-white/60">
          <summary className="cursor-pointer text-white/70">
            {isHebrew ? "מקורות שנבדקו" : "Sources checked"} ({sources.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {sources.map((s, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className={`font-mono text-[10px] px-1.5 rounded ${
                  s.status === "hit"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : s.status === "miss"
                      ? "bg-white/10 text-white/50"
                      : s.status === "skipped"
                        ? "bg-sky-500/15 text-sky-300"
                        : "bg-red-500/15 text-red-300"
                }`}>
                  {String(s.status)}
                </span>
                <span className="flex-1">
                  <span className="text-white/80">{String(s.source)}</span>
                  {s.error != null && (
                    <span className="ml-2 text-white/40">· {String(s.error)}</span>
                  )}
                  {s.url != null && (
                    <a
                      href={String(s.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-2 text-emerald-300 hover:underline"
                    >
                      {isHebrew ? "קישור" : "link"}
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ul>
          {verbatim && (
            <button
              type="button"
              onClick={() => runExtract(true)}
              disabled={extracting}
              className="mt-2 text-[11px] text-white/50 hover:text-white/80 underline disabled:opacity-40"
            >
              {extracting
                ? isHebrew
                  ? "מרענן…"
                  : "Refreshing…"
                : isHebrew
                  ? "רענן חילוץ"
                  : "Re-run extraction"}
            </button>
          )}
        </details>
      )}

      <AuthorProfileDrawer
        openalexId={activeAuthorOpenalex}
        onClose={() => setActiveAuthorOpenalex(null)}
        isHebrew={isHebrew}
      />
    </div>
  );
}
