"""Internet Archive client — Chappie's window into the cultural record.

archive.org holds millions of scanned books, historical texts, and
primary documents that OpenAlex (journal-centric) never sees. This is
the "not only science" memory: philosophy classics, primary sources,
the history of ideas.

Two free APIs, no key:
- Advanced Search (scholar-style metadata query)
- Metadata API (per-item details + full-text availability)

Returns records normalized to Korczak's paper schema, tagged
source='internet_archive' so the verification court and trust registry
(Internet Archive is a Tier-3 trusted source) handle them correctly.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata"
IA_DETAILS = "https://archive.org/details"


async def search_archive(
    query: str,
    limit: int = 10,
    media_type: str = "texts",
    year_from: int | None = None,
) -> list[dict]:
    """Search the Internet Archive's texts collection.

    Prioritizes items with full text available (a real reading room, not
    just metadata). Returns records in Korczak's paper shape.
    """
    q = f'({query}) AND mediatype:{media_type}'
    if year_from:
        q += f" AND year:[{year_from} TO 2026]"

    params = {
        "q": q,
        "fl[]": ["identifier", "title", "creator", "year", "description",
                 "subject", "downloads", "language"],
        "sort[]": "downloads desc",   # a rough popularity/importance proxy
        "rows": min(limit, 30),
        "page": 1,
        "output": "json",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(IA_SEARCH, params=params, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"Internet Archive search error: {resp.status_code}")
                return []
            docs = resp.json().get("response", {}).get("docs", [])
    except Exception as e:
        logger.warning(f"Internet Archive search failed: {e}")
        return []

    records = []
    for d in docs:
        creator = d.get("creator")
        if isinstance(creator, list):
            authors = [{"name": c} for c in creator[:6]]
        elif creator:
            authors = [{"name": creator}]
        else:
            authors = []

        year = d.get("year")
        try:
            year = int(str(year)[:4]) if year else None
        except (ValueError, TypeError):
            year = None

        ident = d.get("identifier", "")
        records.append({
            "title": d.get("title", "") if isinstance(d.get("title"), str)
                     else (d.get("title") or [""])[0],
            "authors": authors,
            "publication_year": year,
            "abstract": (d.get("description") or "")[:1500]
                        if isinstance(d.get("description"), str)
                        else (" ".join(d.get("description") or [])[:1500]),
            "cited_by_count": int(d.get("downloads", 0) or 0),  # downloads as impact proxy
            "doi": None,
            "venue": "Internet Archive",
            "subjects": d.get("subject") if isinstance(d.get("subject"), list) else [d.get("subject")] if d.get("subject") else [],
            "source": "internet_archive",
            "external_id": ident,
            "url": f"{IA_DETAILS}/{ident}" if ident else None,
        })
    return records


async def get_fulltext_availability(identifier: str) -> dict:
    """Check whether an Archive item has readable full text and where.

    Returns {has_fulltext, formats, read_url, txt_url}.
    Chappie can actually READ these — a genuine reading room for primary texts.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{IA_METADATA}/{identifier}", timeout=15)
            if resp.status_code != 200:
                return {"has_fulltext": False}
            data = resp.json()
    except Exception as e:
        logger.debug(f"IA metadata failed for {identifier}: {e}")
        return {"has_fulltext": False}

    files = data.get("files", [])
    txt_files = [f for f in files if f.get("format") in ("Text", "DjVuTXT", "Plain Text")]
    has_readable = any(
        f.get("format") in ("DjVuTXT", "Text", "Plain Text", "Abbyy GZ") for f in files
    )
    txt_url = None
    if txt_files:
        txt_url = f"https://archive.org/download/{identifier}/{txt_files[0]['name']}"

    return {
        "has_fulltext": has_readable,
        "read_url": f"{IA_DETAILS}/{identifier}",
        "txt_url": txt_url,
        "formats": sorted({f.get("format", "") for f in files if f.get("format")}),
    }


async def fetch_fulltext_excerpt(txt_url: str, max_chars: int = 8000) -> str:
    """Fetch the opening of a public-domain full text for grounded reading.

    Bounded — we read an excerpt for grounding/synthesis, not the whole book.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(txt_url, timeout=25)
            if resp.status_code == 200:
                return resp.text[:max_chars]
    except Exception as e:
        logger.debug(f"IA fulltext fetch failed: {e}")
    return ""
