"""Echo sources — reading a moment's textual wake.

Significant footage leaves ripples in text: news coverage, TV replays, a
surge of Wikipedia readers, a spike of searches. These free signals point at
WHICH moment mattered and WHEN, and the articles they surface carry the
interpretation the culture gave the moment — Layer-1 material, human-written.

All free, no key required:
- GDELT DOC 2.0  : global news coverage volume + top articles over time
- GDELT TV 2.0   : how much airtime a moment got on TV news (the "replay")
- Wikipedia      : daily pageviews per article (attention spikes)
- Google Trends  : optional, fragile (needs pytrends) — rising queries

Each function degrades gracefully to [] / {} on failure — the pipeline
combines whatever signals answered.
"""

import logging
from datetime import date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Korczak/1.0 (knowledge navigator; echo layer)"}


# ---------------------------------------------------------------------------
# GDELT — news coverage & TV replays (the strongest signal)
# ---------------------------------------------------------------------------

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_TV = "https://api.gdeltproject.org/api/v2/tv/tv"


async def gdelt_news_timeline(query: str, years_back: int = 25) -> list[dict]:
    """Daily/weekly news-coverage volume for a query. Reveals when it peaked.

    Returns [{date: 'YYYY-MM-DD', value: float}], normalized by GDELT.
    """
    end = datetime.utcnow()
    start = end - timedelta(days=365 * years_back)
    params = {
        "query": query,
        "mode": "timelinevol",
        "format": "json",
        "startdatetime": start.strftime("%Y%m%d000000"),
        "enddatetime": end.strftime("%Y%m%d000000"),
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(GDELT_DOC, params=params, headers=_UA, timeout=25)
            if resp.status_code != 200 or not resp.text.strip().startswith("{"):
                return []
            timeline = resp.json().get("timeline", [])
    except Exception as e:
        logger.warning(f"GDELT news timeline failed: {e}")
        return []

    out = []
    for series in timeline:
        for pt in series.get("data", []):
            d = _parse_gdelt_date(pt.get("date"))
            if d:
                out.append({"date": d, "value": float(pt.get("value", 0) or 0)})
        break  # first series = normalized volume
    return out


async def gdelt_top_articles(query: str, start: date | None = None,
                             end: date | None = None, limit: int = 15) -> list[dict]:
    """Top news/analysis articles for a query in a window — the interpretation
    the culture gave the moment. Returns [{title, url, domain, date}]."""
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(limit, 50),
        "sort": "hybridrel",
    }
    if start:
        params["startdatetime"] = start.strftime("%Y%m%d000000")
    if end:
        params["enddatetime"] = end.strftime("%Y%m%d235959")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(GDELT_DOC, params=params, headers=_UA, timeout=25)
            if resp.status_code != 200 or not resp.text.strip().startswith("{"):
                return []
            articles = resp.json().get("articles", [])
    except Exception as e:
        logger.warning(f"GDELT article list failed: {e}")
        return []

    out = []
    for a in articles:
        out.append({
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "domain": a.get("domain", ""),
            "date": _parse_gdelt_date(a.get("seendate", "")),
            "language": a.get("language", ""),
        })
    return out


async def gdelt_tv_timeline(query: str, years_back: int = 15) -> list[dict]:
    """TV-news airtime for a query over time — the 'which moment got replayed'
    signal. Television News Archive covers ~2009 onward. [{date, value}]."""
    end = datetime.utcnow()
    start = end - timedelta(days=365 * years_back)
    params = {
        "query": query,
        "mode": "timelinevol",
        "format": "json",
        "datanorm": "perc",
        "startdatetime": start.strftime("%Y%m%d000000"),
        "enddatetime": end.strftime("%Y%m%d000000"),
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(GDELT_TV, params=params, headers=_UA, timeout=25)
            if resp.status_code != 200 or not resp.text.strip().startswith("{"):
                return []
            timeline = resp.json().get("timeline", [])
    except Exception as e:
        logger.debug(f"GDELT TV timeline failed: {e}")
        return []

    out = []
    for series in timeline:
        for pt in series.get("data", []):
            d = _parse_gdelt_date(pt.get("date"))
            if d:
                out.append({"date": d, "value": float(pt.get("value", 0) or 0)})
        break
    return out


# ---------------------------------------------------------------------------
# Wikipedia — attention spikes (daily pageviews)
# ---------------------------------------------------------------------------

async def wikipedia_resolve_article(query: str, lang: str = "en") -> str | None:
    """Resolve a search term to a Wikipedia article title."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query,
                        "srlimit": 1, "format": "json"},
                headers=_UA, timeout=15,
            )
            if resp.status_code != 200:
                return None
            hits = resp.json().get("query", {}).get("search", [])
            return hits[0]["title"] if hits else None
    except Exception as e:
        logger.debug(f"Wikipedia resolve failed: {e}")
        return None


async def wikipedia_pageviews(article: str, start: date, end: date,
                              lang: str = "en") -> list[dict]:
    """Daily pageviews for an article (data from 2015-07 onward).
    Returns [{date: 'YYYY-MM-DD', value: int}]."""
    title = article.replace(" ", "_")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"{lang}.wikipedia/all-access/all-agents/{httpx.URL(title)}/daily/"
           f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_UA, timeout=20)
            if resp.status_code != 200:
                return []
            items = resp.json().get("items", [])
    except Exception as e:
        logger.debug(f"Wikipedia pageviews failed: {e}")
        return []

    out = []
    for it in items:
        ts = str(it.get("timestamp", ""))[:8]
        if len(ts) == 8:
            out.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "value": int(it.get("views", 0))})
    return out


# ---------------------------------------------------------------------------
# Google Trends — optional, fragile (unofficial; needs pytrends)
# ---------------------------------------------------------------------------

def google_trends_rising(query: str, timeframe: str = "all", geo: str = "") -> list[dict]:
    """Rising related queries around a term. Best-effort — returns [] if
    pytrends is unavailable or rate-limited. Synchronous (pytrends is sync)."""
    try:
        from pytrends.request import TrendReq  # type: ignore
    except Exception:
        logger.debug("pytrends not installed — skipping Google Trends")
        return []
    try:
        pt = TrendReq(hl="en-US", tz=0)
        pt.build_payload([query], timeframe=timeframe, geo=geo)
        related = pt.related_queries().get(query, {}) or {}
        rising = related.get("rising")
        if rising is None:
            return []
        out = []
        for _, row in rising.iterrows():
            out.append({"term": str(row.get("query", "")), "value": float(row.get("value", 0) or 0)})
        return out[:15]
    except Exception as e:
        logger.debug(f"Google Trends failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Spike detection — find the moments a timeline peaked
# ---------------------------------------------------------------------------

def detect_spikes(series: list[dict], top_n: int = 3, min_z: float = 2.0) -> list[dict]:
    """Find the top peaks in a [{date, value}] series (z-score over the mean).

    Returns [{date, value, z, strength}] sorted by strength, strength in 0..1.
    """
    vals = [p["value"] for p in series if p.get("value") is not None]
    if len(vals) < 4:
        return []
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = var ** 0.5 or 1.0
    peak = max(vals) or 1.0

    scored = []
    for p in series:
        v = p.get("value") or 0
        z = (v - mean) / std
        if z >= min_z:
            scored.append({"date": p["date"], "value": v, "z": round(z, 2),
                           "strength": round(min(1.0, v / peak), 3)})
    scored.sort(key=lambda x: x["strength"], reverse=True)
    return scored[:top_n]


def _parse_gdelt_date(s: str) -> str | None:
    """GDELT dates: 'YYYYMMDDTHHMMSSZ' or 'YYYYMMDDHHMMSS' → 'YYYY-MM-DD'."""
    if not s:
        return None
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None
