"use client";

import { useEffect, useState } from "react";

import {
  type AuthorProfile,
  getAuthorProfileByOpenAlex,
  getAuthorProfilePapers,
} from "@/lib/api";

interface Props {
  openalexId: string | null | undefined;
  onClose: () => void;
  isHebrew?: boolean;
}

type PaperRow = {
  id: string;
  title?: string | null;
  publication_year?: number | null;
  cited_by_count?: number | null;
  doi?: string | null;
  access_status?: string | null;
  access_url?: string | null;
};

/**
 * Slide-in drawer that shows an author's background and their papers in the
 * corpus. First view of an un-enriched profile triggers inline OpenAlex
 * fetch + Claude bio generation (handled server-side by /profile/by-openalex).
 */
export function AuthorProfileDrawer({ openalexId, onClose, isHebrew = false }: Props) {
  const [profile, setProfile] = useState<AuthorProfile | null>(null);
  const [papers, setPapers] = useState<PaperRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!openalexId) return;

    setProfile(null);
    setPapers([]);
    setError(null);
    setLoading(true);

    (async () => {
      try {
        const p = await getAuthorProfileByOpenAlex(openalexId);
        if (cancelled) return;
        setProfile(p);
        if (p.id) {
          const { papers: rows } = await getAuthorProfilePapers(p.id, 20);
          if (!cancelled) setPapers(rows as PaperRow[]);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [openalexId]);

  if (!openalexId) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex"
      dir={isHebrew ? "rtl" : "ltr"}
      onClick={onClose}
    >
      <div className="flex-1 bg-black/50 backdrop-blur-sm" />
      <aside
        className="w-full max-w-md h-full bg-neutral-950 border-l border-white/10 overflow-y-auto p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-xl font-semibold text-white">
            {isHebrew ? "פרופיל מחבר" : "Author profile"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label={isHebrew ? "סגור" : "Close"}
            className="text-white/60 hover:text-white text-lg leading-none"
          >
            ×
          </button>
        </div>

        {loading && (
          <p className="text-sm text-white/50">
            {isHebrew ? "טוען פרטי מחבר…" : "Loading author details…"}
          </p>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}

        {profile && (
          <div className="space-y-4">
            <div>
              <h4 className="text-lg font-medium text-white">{profile.name}</h4>
              {profile.primary_institution && (
                <p className="text-sm text-white/70 mt-1">
                  {profile.primary_institution}
                  {profile.country ? ` · ${profile.country}` : ""}
                </p>
              )}
              {profile.primary_field && (
                <p className="text-xs text-white/50 mt-1 uppercase tracking-wider">
                  {profile.primary_field}
                </p>
              )}
            </div>

            {profile.bio && (
              <p className="text-sm text-white/80 leading-relaxed">{profile.bio}</p>
            )}

            <div className="flex flex-wrap gap-3 text-xs text-white/60">
              {typeof profile.works_count === "number" && (
                <span>
                  {isHebrew ? "מאמרים" : "Works"}: {profile.works_count}
                </span>
              )}
              {typeof profile.cited_by_count === "number" && (
                <span>
                  {isHebrew ? "ציטוטים" : "Cited by"}: {profile.cited_by_count}
                </span>
              )}
              {typeof profile.h_index === "number" && profile.h_index !== null && (
                <span>h-index: {profile.h_index}</span>
              )}
            </div>

            {profile.institution_history && profile.institution_history.length > 0 && (
              <details className="text-sm text-white/70">
                <summary className="cursor-pointer text-white/80">
                  {isHebrew ? "היסטוריית מוסדות" : "Institution history"}
                </summary>
                <ul className="mt-2 space-y-1 list-disc list-inside">
                  {profile.institution_history.slice(0, 6).map((h, idx) => (
                    <li key={idx}>
                      {h.institution || "?"}
                      {h.country ? ` · ${h.country}` : ""}
                      {h.years && h.years.length > 0 && ` (${h.years[0]}–${h.years[h.years.length - 1]})`}
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div>
              <h5 className="text-sm font-medium text-white/80 mb-2">
                {isHebrew ? "מאמרים במערכת" : "Papers in our corpus"}
              </h5>
              {papers.length === 0 ? (
                <p className="text-xs text-white/50">
                  {isHebrew ? "לא נמצאו מאמרים" : "No papers found in corpus."}
                </p>
              ) : (
                <ul className="space-y-2">
                  {papers.map((p) => (
                    <li
                      key={p.id}
                      className="text-xs text-white/70 bg-white/5 rounded p-2 border border-white/5"
                    >
                      <div className="text-white/90 font-medium leading-snug">
                        {p.title || "(untitled)"}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-white/50">
                        {p.publication_year && <span>{p.publication_year}</span>}
                        {typeof p.cited_by_count === "number" && (
                          <span>· {p.cited_by_count} cites</span>
                        )}
                        {p.access_url && (
                          <a
                            href={p.access_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-auto text-emerald-400 hover:underline"
                          >
                            {p.access_status || "read"}
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
