"""Unpaywall source — re-check OA status in case a paper opened since seed.

Returns an URL the user can visit (no passage text — full-text scraping
is the job of fetch_full_text.py / the full_text cache). The aggregator
uses this as a fallback link when no in-text passage can be found.
"""

import os
import re

import httpx

from backend.core.provenance.types import ExtractionContext, SourceResult


UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
_EMAIL = os.getenv("OPENALEX_EMAIL", "")


async def fetch(ctx: ExtractionContext) -> SourceResult:
    if not ctx.doi:
        return SourceResult(source="unpaywall", status="miss", error="no DOI")
    if not _EMAIL:
        return SourceResult(source="unpaywall", status="skipped", error="OPENALEX_EMAIL not set")

    clean_doi = re.sub(r"^https?://doi\.org/", "", ctx.doi)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{UNPAYWALL_BASE}/{clean_doi}",
                params={"email": _EMAIL},
                timeout=15,
            )
    except Exception as e:
        return SourceResult(source="unpaywall", status="error", error=str(e))

    if resp.status_code != 200:
        return SourceResult(source="unpaywall", status="miss", error=f"HTTP {resp.status_code}")

    data = resp.json()
    is_oa = bool(data.get("is_oa"))
    best = data.get("best_oa_location") or {}
    url = best.get("url_for_landing_page") or best.get("url") or best.get("url_for_pdf")

    if not url:
        return SourceResult(
            source="unpaywall",
            status="miss",
            error="no OA location",
            extra={"is_oa": is_oa},
        )

    return SourceResult(
        source="unpaywall",
        status="hit",
        url=url,
        extra={
            "is_oa": is_oa,
            "version": best.get("version"),
            "host_type": best.get("host_type"),
        },
    )
