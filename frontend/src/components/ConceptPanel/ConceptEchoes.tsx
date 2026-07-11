"use client";

import { useEffect, useState } from "react";
import { Radio, Newspaper, Tv, TrendingUp, Search, Loader2, ExternalLink } from "lucide-react";
import { getConceptEchoes, analyzeConceptEchoes, type EchoItem } from "@/lib/api";
import { useLocaleStore } from "@/stores/localeStore";

const KIND_META: Record<
  string,
  { icon: typeof Radio; en: string; he: string; cls: string }
> = {
  news_volume: { icon: Newspaper, en: "peak coverage", he: "שיא כיסוי", cls: "text-accent-blue" },
  tv_replay: { icon: Tv, en: "TV replay", he: "שידור חוזר", cls: "text-accent-purple" },
  attention_spike: { icon: TrendingUp, en: "attention spike", he: "קפיצת קשב", cls: "text-accent-green" },
  rising_query: { icon: Search, en: "people searched", he: "אנשים חיפשו", cls: "text-accent-amber" },
  analysis: { icon: Newspaper, en: "analysis", he: "ניתוח", cls: "text-text-secondary" },
};

export default function ConceptEchoes({ conceptId }: { conceptId: string }) {
  const { locale } = useLocaleStore();
  const he = locale === "he";
  const [echoes, setEchoes] = useState<EchoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    setLoading(true);
    getConceptEchoes(conceptId)
      .then(setEchoes)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [conceptId]);

  const handleAnalyze = async () => {
    if (analyzing) return;
    setAnalyzing(true);
    try {
      const items = await analyzeConceptEchoes(conceptId);
      if (items.length) setEchoes(items);
    } catch {
      /* graceful */
    } finally {
      setAnalyzing(false);
    }
  };

  const moments = echoes.filter((e) => e.kind !== "analysis");
  const analyses = echoes.filter((e) => e.kind === "analysis" && e.url);

  if (loading) return null;

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h3 className="section-header flex items-center gap-2">
          <Radio size={12} />
          {he ? "הד הרגע" : "The moment's wake"}
        </h3>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="text-[10px] text-text-tertiary hover:text-accent-gold flex items-center gap-1 disabled:opacity-40 transition-colors"
          title={he ? "קרא את התגובה הטקסטואלית סביב הרגע" : "Read the textual response around the moment"}
        >
          {analyzing ? <Loader2 size={11} className="animate-spin" /> : <Radio size={11} />}
          {analyzing ? (he ? "מאזין…" : "listening…") : he ? "נתח הד" : "read the wake"}
        </button>
      </div>

      {echoes.length === 0 ? (
        <p className="text-[11px] text-text-tertiary">
          {he
            ? "נזהה מתי הרגע הזה הכי הדהד — בכיסוי חדשותי, בשידורים חוזרים ובחיפושים."
            : "We'll find when this moment echoed loudest — in news, TV replays, and searches."}
        </p>
      ) : (
        <div className="space-y-3">
          {/* The moments — when it echoed loudest */}
          {moments.length > 0 && (
            <div className="space-y-1.5">
              {moments.slice(0, 6).map((e) => {
                const meta = KIND_META[e.kind] || KIND_META.analysis;
                return (
                  <div key={e.id} className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-surface-sunken">
                    <meta.icon size={12} className={meta.cls} />
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] text-foreground truncate">
                        {e.term || e.headline}
                      </p>
                      <p className="text-[9px] text-text-tertiary">
                        {(he ? meta.he : meta.en)}
                        {e.moment_date ? ` · ${e.moment_date}` : ""}
                        {e.excerpt ? ` · ${e.excerpt}` : ""}
                      </p>
                    </div>
                    {/* strength bar */}
                    <div className="w-8 h-1 rounded-full bg-surface overflow-hidden flex-shrink-0">
                      <div
                        className="h-full bg-accent-gold"
                        style={{ width: `${Math.round(e.signal_strength * 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* The interpretation the culture gave it */}
          {analyses.length > 0 && (
            <div>
              <p className="text-[10px] text-text-tertiary mb-1.5">
                {he ? "איך פירשו את זה אז:" : "How it was read at the time:"}
              </p>
              <div className="space-y-1">
                {analyses.slice(0, 5).map((e) => (
                  <a
                    key={e.id}
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-[11px] text-accent-blue hover:text-accent-gold transition-colors group"
                  >
                    <ExternalLink size={10} className="flex-shrink-0 opacity-60 group-hover:opacity-100" />
                    <span className="truncate">{e.headline}</span>
                    {e.excerpt && <span className="text-[9px] text-text-tertiary flex-shrink-0">{e.excerpt}</span>}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
