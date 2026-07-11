"""Media sources — video/image/audio adapters for "media as evidence".

Unified search across the cultural media record, normalized to one shape so
the interpreter and the UI never care which source a clip came from. New
sources (YouTube today, others tomorrow) plug in without touching callers.

Sources:
- internet_archive : movies/audio (free, no key) — founding footage, speeches
- wikimedia        : Commons images/video (free, no key) — portraits, moments
- youtube          : specific clips (search needs YOUTUBE_API_KEY; a pasted
                     URL works with no key via oEmbed — the "contributor" path)

Every record is embeddable IN the interface (embed_url), never a link-out.
Transcript fetch is best-effort per source; a missing transcript degrades
gracefully (interpretation leans on title/description/context, lower grounding).
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internet Archive — movies & audio (the founding-footage vault)
# ---------------------------------------------------------------------------

async def search_archive_media(query: str, limit: int = 6, media_type: str = "movies") -> list[dict]:
    """Search archive.org movies/audio. media_type: 'movies' | 'audio'."""
    q = f"({query}) AND mediatype:{media_type}"
    params = {
        "q": q,
        "fl[]": ["identifier", "title", "creator", "year", "description", "downloads"],
        "sort[]": "downloads desc",
        "rows": min(limit, 20),
        "output": "json",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://archive.org/advancedsearch.php", params=params, timeout=20)
            if resp.status_code != 200:
                return []
            docs = resp.json().get("response", {}).get("docs", [])
    except Exception as e:
        logger.warning(f"Archive media search failed: {e}")
        return []

    out = []
    for d in docs:
        ident = d.get("identifier", "")
        if not ident:
            continue
        title = d.get("title", "")
        if isinstance(title, list):
            title = title[0] if title else ""
        desc = d.get("description") or ""
        if isinstance(desc, list):
            desc = " ".join(desc)
        out.append({
            "source": "internet_archive",
            "external_id": ident,
            "media_kind": "audio" if media_type == "audio" else "video",
            "title": title[:400],
            "description": desc[:1500],
            "embed_url": f"https://archive.org/embed/{ident}",
            "page_url": f"https://archive.org/details/{ident}",
            "thumbnail_url": f"https://archive.org/services/img/{ident}",
            "duration_seconds": None,
        })
    return out


# ---------------------------------------------------------------------------
# Wikimedia Commons — images & video (portraits, moments, public-domain media)
# ---------------------------------------------------------------------------

async def search_wikimedia(query: str, limit: int = 6) -> list[dict]:
    """Search Wikimedia Commons for images/video (free, no key)."""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap|video {query}", "gsrnamespace": 6,
        "gsrlimit": min(limit, 20),
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://commons.wikimedia.org/w/api.php", params=params,
                headers={"User-Agent": "Korczak/1.0 (knowledge navigator)"}, timeout=20,
            )
            if resp.status_code != 200:
                return []
            pages = resp.json().get("query", {}).get("pages", {})
    except Exception as e:
        logger.warning(f"Wikimedia search failed: {e}")
        return []

    out = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        kind = "video" if mime.startswith("video") else "image"
        meta = info.get("extmetadata") or {}
        desc = re.sub(r"<[^>]+>", "", (meta.get("ImageDescription", {}) or {}).get("value", "") or "")
        out.append({
            "source": "wikimedia",
            "external_id": p.get("title", ""),
            "media_kind": kind,
            "title": (p.get("title", "") or "").replace("File:", "")[:400],
            "description": desc[:1500],
            "embed_url": info.get("thumburl") or info.get("url"),   # <img> src
            "page_url": info.get("descriptionurl"),
            "thumbnail_url": info.get("thumburl") or info.get("url"),
            "duration_seconds": None,
        })
    return out


# ---------------------------------------------------------------------------
# YouTube — specific clips. Search needs a key; a pasted URL needs none.
# ---------------------------------------------------------------------------

_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def youtube_id_from_url(url: str) -> str | None:
    """Extract a video id from any YouTube URL shape (the contributor path)."""
    m = _YT_ID_RE.search(url or "")
    return m.group(1) if m else None


async def youtube_from_url(url: str) -> dict | None:
    """Resolve a pasted YouTube URL to an embeddable record — NO api key needed.

    This is the lecturer/researcher contribution path: they point at the clip
    that illustrates their claim; oEmbed gives us the title + thumbnail.
    """
    vid = youtube_id_from_url(url)
    if not vid:
        return None
    title, thumb = "", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", "")
                thumb = data.get("thumbnail_url", thumb)
    except Exception as e:
        logger.debug(f"YouTube oEmbed failed for {vid}: {e}")

    return {
        "source": "youtube",
        "external_id": vid,
        "media_kind": "video",
        "title": title[:400],
        "description": "",
        "embed_url": f"https://www.youtube.com/embed/{vid}",
        "page_url": f"https://www.youtube.com/watch?v={vid}",
        "thumbnail_url": thumb,
        "duration_seconds": None,
    }


async def search_youtube(query: str, limit: int = 6) -> list[dict]:
    """Search YouTube (needs YOUTUBE_API_KEY). Returns [] with no key."""
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        logger.debug("YouTube search skipped: no YOUTUBE_API_KEY")
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"key": key, "q": query, "part": "snippet", "type": "video",
                        "maxResults": min(limit, 15)},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            items = resp.json().get("items", [])
    except Exception as e:
        logger.warning(f"YouTube search failed: {e}")
        return []

    out = []
    for it in items:
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if not vid:
            continue
        out.append({
            "source": "youtube",
            "external_id": vid,
            "media_kind": "video",
            "title": (sn.get("title") or "")[:400],
            "description": (sn.get("description") or "")[:1500],
            "embed_url": f"https://www.youtube.com/embed/{vid}",
            "page_url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail_url": (((sn.get("thumbnails") or {}).get("high") or {}).get("url"))
                             or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "duration_seconds": None,
        })
    return out


# ---------------------------------------------------------------------------
# Transcript (Layer 0) — best-effort per source
# ---------------------------------------------------------------------------

async def fetch_transcript(record: dict, max_chars: int = 6000) -> str:
    """Best-effort transcript/captions for a record. Empty string if none."""
    source = record.get("source")
    try:
        if source == "youtube":
            return await _youtube_captions(record["external_id"], max_chars)
        if source == "internet_archive":
            return await _archive_captions(record["external_id"], max_chars)
    except Exception as e:
        logger.debug(f"Transcript fetch failed ({source}): {e}")
    return ""


async def _youtube_captions(video_id: str, max_chars: int) -> str:
    """Fetch public timed-text captions (no key). Not all videos expose these."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for lang in ("en", "he", "iw"):
            resp = await client.get(
                "https://www.youtube.com/api/timedtext",
                params={"lang": lang, "v": video_id}, timeout=15,
            )
            if resp.status_code == 200 and resp.text.strip():
                text = re.sub(r"<[^>]+>", " ", resp.text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    return text[:max_chars]
    return ""


async def _archive_captions(identifier: str, max_chars: int) -> str:
    """Pull an .srt/.vtt caption file from an archive.org item if present."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        meta = await client.get(f"https://archive.org/metadata/{identifier}", timeout=15)
        if meta.status_code != 200:
            return ""
        files = meta.json().get("files", [])
        cap = next((f for f in files if str(f.get("name", "")).lower().endswith((".srt", ".vtt"))), None)
        if not cap:
            return ""
        c = await client.get(f"https://archive.org/download/{identifier}/{cap['name']}", timeout=20)
        if c.status_code != 200:
            return ""
        # strip timestamps/indices → plain spoken text
        lines = [ln for ln in c.text.splitlines()
                 if ln.strip() and "-->" not in ln and not ln.strip().isdigit()]
        return re.sub(r"\s+", " ", " ".join(lines)).strip()[:max_chars]


# ---------------------------------------------------------------------------
# Unified search
# ---------------------------------------------------------------------------

async def search_media(query: str, limit_per_source: int = 4,
                       sources: list[str] | None = None) -> list[dict]:
    """Search media sources in parallel, deduped. Default: archive + wikimedia
    (+ youtube only if a key is configured)."""
    import asyncio

    picks = sources or ["internet_archive", "wikimedia"]
    if "youtube" not in picks and os.getenv("YOUTUBE_API_KEY"):
        picks.append("youtube")

    fns = {
        "internet_archive": lambda: search_archive_media(query, limit_per_source, "movies"),
        "wikimedia": lambda: search_wikimedia(query, limit_per_source),
        "youtube": lambda: search_youtube(query, limit_per_source),
    }
    tasks = {n: fns[n]() for n in picks if n in fns}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    out, seen = [], set()
    for res in results:
        if isinstance(res, Exception):
            continue
        for r in res:
            key = (r["source"], r["external_id"])
            if key not in seen:
                seen.add(key)
                out.append(r)
    return out
