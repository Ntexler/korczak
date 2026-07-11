"""Echo pipeline — find which moment mattered from its textual wake.

Given a concept (an event/idea), this fuses free signals to locate the
moments that generated the most human response, and pulls the analysis those
moments provoked (the interpretation the culture gave them):

  1. GDELT news volume over ~25y  → peak moments (self-anchoring: no known
     date needed; the wake reveals WHEN it happened)
  2. Around each peak, GDELT top articles → op-eds/analysis (Layer-1 material)
  3. GDELT TV airtime → which moments got REPLAYED on television
  4. Wikipedia daily pageviews → attention spikes (2015+ )
  5. Google Trends rising queries → what people suddenly searched (optional)

The cheap textual layer does the heavy lifting; expensive visual analysis
(the "Bibi's face" pass) becomes a targeted last step at an identified moment.

Usage:
  python -m backend.agents.echo_pipeline --concept <uuid>
  python -m backend.agents.echo_pipeline --limit 10   # sweep event concepts
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_EVENT_TYPES = ("phenomenon", "paradigm", "critique")


def _window_around(d: str, days: int = 5) -> tuple[date, date]:
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    return dt - timedelta(days=days), dt + timedelta(days=days)


async def analyze_concept(client, concept: dict, store: bool = True) -> dict:
    """Run the echo pipeline for one concept. Returns the collected echoes."""
    from backend.integrations import echo_sources as es

    name = concept["name"]
    echoes: list[dict] = []

    # 1) News volume → peak moments
    news = await es.gdelt_news_timeline(name)
    news_peaks = es.detect_spikes(news, top_n=3)

    # 2) For each peak, the analysis it provoked + record the moment itself
    for peak in news_peaks:
        echoes.append({
            "kind": "news_volume", "source": "gdelt",
            "moment_date": peak["date"], "signal_strength": peak["strength"],
            "headline": f"Peak news coverage of \"{name}\"",
            "url": None, "excerpt": f"z={peak['z']} above baseline", "term": None,
        })
        start, end = _window_around(peak["date"], days=7)
        for art in (await es.gdelt_top_articles(name, start, end, limit=6)):
            if not art.get("url"):
                continue
            echoes.append({
                "kind": "analysis", "source": "gdelt",
                "moment_date": art.get("date") or peak["date"],
                "signal_strength": peak["strength"],
                "headline": art.get("title", "")[:300],
                "url": art["url"], "excerpt": art.get("domain", ""), "term": None,
            })

    # 3) TV replays
    tv_peaks = es.detect_spikes(await es.gdelt_tv_timeline(name), top_n=3)
    for peak in tv_peaks:
        echoes.append({
            "kind": "tv_replay", "source": "gdelt",
            "moment_date": peak["date"], "signal_strength": peak["strength"],
            "headline": f"\"{name}\" replayed on TV news",
            "url": None, "excerpt": f"airtime peak (z={peak['z']})", "term": None,
        })

    # 4) Wikipedia attention spikes (only meaningful for moments after 2015-07)
    article = await es.wikipedia_resolve_article(name)
    if article:
        pv = await es.wikipedia_pageviews(article, date(2015, 7, 1), datetime.utcnow().date())
        for peak in es.detect_spikes(pv, top_n=3, min_z=3.0):
            echoes.append({
                "kind": "attention_spike", "source": "wikipedia",
                "moment_date": peak["date"], "signal_strength": peak["strength"],
                "headline": f"Wikipedia readers surged to \"{article}\"",
                "url": f"https://en.wikipedia.org/wiki/{article.replace(' ', '_')}",
                "excerpt": f"{int(peak['value'])} views/day (z={peak['z']})", "term": None,
            })

    # 5) Google Trends rising queries (optional, sync, best-effort)
    for rq in es.google_trends_rising(name):
        echoes.append({
            "kind": "rising_query", "source": "google_trends",
            "moment_date": None, "signal_strength": min(1.0, rq["value"] / 100.0),
            "headline": f"People searched: \"{rq['term']}\"",
            "url": None, "excerpt": None, "term": rq["term"],
        })

    if store and echoes:
        _store(client, concept["id"], echoes)

    return {"concept": name, "moments": len(news_peaks),
            "tv_moments": len(tv_peaks), "echoes": len(echoes), "items": echoes}


def _store(client, concept_id: str, echoes: list[dict]) -> None:
    """Replace this concept's echoes with the fresh scan."""
    try:
        client.table("concept_echoes").delete().eq("concept_id", concept_id).execute()
    except Exception as e:
        logger.debug(f"echo clear failed: {e}")
    rows = [{**e, "concept_id": concept_id} for e in echoes[:80]]
    try:
        client.table("concept_echoes").insert(rows).execute()
    except Exception as e:
        logger.warning(f"echo insert failed: {e}")


async def sweep(limit: int = 10) -> dict:
    """Run the echo pipeline over the most prominent event concepts."""
    from backend.integrations.supabase_client import get_client
    client = get_client()
    res = (client.table("concepts").select("id,name,type")
           .in_("type", list(_EVENT_TYPES))
           .order("paper_count", desc=True).limit(limit).execute())
    totals = {"concepts": 0, "echoes": 0}
    for c in (res.data or []):
        r = await analyze_concept(client, c)
        totals["concepts"] += 1
        totals["echoes"] += r["echoes"]
        logger.info(f"  {c['name']}: {r['echoes']} echoes across {r['moments']} moments")
    return totals


async def main():
    parser = argparse.ArgumentParser(description="Echo pipeline — a moment's textual wake")
    parser.add_argument("--concept", default=None, help="concept UUID")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from backend.integrations.supabase_client import get_client
    client = get_client()
    if args.concept:
        res = client.table("concepts").select("id,name,type").eq("id", args.concept).limit(1).execute()
        c = (res.data or [None])[0]
        if not c:
            print("concept not found"); return
        import json
        print(json.dumps(await analyze_concept(client, c), indent=2, ensure_ascii=False))
    else:
        print(await sweep(args.limit))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
