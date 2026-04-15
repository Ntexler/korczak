"""CORE API source — large open-access aggregator.

Returns abstract (more often than not, truncated) and a download URL
when the paper is in CORE's index. Free-tier rate limits are strict;
this source is best-effort.
"""

import os
import re

import httpx

from backend.core.provenance.types import ExtractionContext, SourceResult


CORE_BASE = "https://api.core.ac.uk/v3"
_API_KEY = os.getenv("CORE_API_KEY")


async def fetch(ctx: ExtractionContext) -> SourceResult:
    if not ctx.doi:
        return SourceResult(source="core", status="miss", error="no DOI")
    if not _API_KEY:
        return SourceResult(source="core", status="skipped", error="CORE_API_KEY not set")

    clean_doi = re.sub(r"^https?://doi\.org/", "", ctx.doi)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CORE_BASE}/search/works",
                params={"q": f"doi:{clean_doi}", "limit": 1},
                headers={"Authorization": f"Bearer {_API_KEY}"},
                timeout=15,
            )
    except Exception as e:
        return SourceResult(source="core", status="error", error=str(e))

    if resp.status_code == 429:
        return SourceResult(source="core", status="error", error="rate_limited")
    if resp.status_code != 200:
        return SourceResult(source="core", status="miss", error=f"HTTP {resp.status_code}")

    data = resp.json()
    results = data.get("results") or []
    if not results:
        return SourceResult(source="core", status="miss", error="no match")

    work = results[0]
    passages = []
    hints = []

    abstract = work.get("abstract")
    if abstract:
        passages.append(abstract.strip())
        hints.append("CORE abstract")

    download_url = work.get("downloadUrl")
    landing = work.get("sourceFulltextUrls") or []
    url = download_url or (landing[0] if landing else None)

    if not passages and not url:
        return SourceResult(source="core", status="miss", error="empty record")

    return SourceResult(
        source="core",
        status="hit",
        passages=passages,
        location_hints=hints,
        url=url,
    )
