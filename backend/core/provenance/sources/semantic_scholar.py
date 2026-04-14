"""Semantic Scholar source.

Returns two kinds of candidate passages:
  1. The paper's TLDR (summary) — grounding signal but not a verbatim quote
  2. "Citation contexts" — passages from *citing* papers that quote or
     discuss this paper's claims. These are genuine verbatim passages of
     how the work has been used in the literature, which is useful when
     the paper itself isn't open-access.

Also returns an OA PDF URL when Semantic Scholar knows of one.
"""

import os
import re

import httpx

from backend.core.provenance.types import ExtractionContext, SourceResult


S2_BASE = "https://api.semanticscholar.org/graph/v1"
_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")  # Optional but raises rate limits

_MAX_CITATION_CONTEXTS = 8


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if _API_KEY:
        h["x-api-key"] = _API_KEY
    return h


async def fetch(ctx: ExtractionContext) -> SourceResult:
    if not ctx.doi:
        return SourceResult(source="semantic_scholar", status="miss", error="no DOI")

    clean_doi = re.sub(r"^https?://doi\.org/", "", ctx.doi)
    fields = "tldr,abstract,openAccessPdf,citations.contexts,citations.isInfluential"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{S2_BASE}/paper/DOI:{clean_doi}",
                params={"fields": fields},
                headers=_headers(),
                timeout=20,
            )
    except Exception as e:
        return SourceResult(source="semantic_scholar", status="error", error=str(e))

    if resp.status_code == 429:
        return SourceResult(source="semantic_scholar", status="error", error="rate_limited")
    if resp.status_code != 200:
        return SourceResult(source="semantic_scholar", status="miss", error=f"HTTP {resp.status_code}")

    data = resp.json()
    passages: list[str] = []
    hints: list[str | None] = []

    # (1) TLDR — useful framing signal for the aggregator, labelled as not-verbatim
    tldr = (data.get("tldr") or {}).get("text")
    if tldr:
        passages.append(tldr)
        hints.append("S2 TLDR (auto-summary, not a verbatim quote from the paper)")

    # (2) Citation contexts from influential citing papers (when available)
    citations = data.get("citations") or []
    citation_passages: list[tuple[str, str]] = []  # (passage, hint)
    for cit in citations:
        contexts = cit.get("contexts") or []
        for ctxt in contexts:
            if not ctxt:
                continue
            hint = "Citation context (from a paper citing this work)"
            if cit.get("isInfluential"):
                hint = "Citation context (influential citing paper)"
            citation_passages.append((ctxt.strip(), hint))
        if len(citation_passages) >= _MAX_CITATION_CONTEXTS:
            break
    for p, h in citation_passages[:_MAX_CITATION_CONTEXTS]:
        passages.append(p)
        hints.append(h)

    oa_pdf = (data.get("openAccessPdf") or {}).get("url") if isinstance(data.get("openAccessPdf"), dict) else None

    if not passages and not oa_pdf:
        return SourceResult(source="semantic_scholar", status="miss", error="no passages or PDF")

    return SourceResult(
        source="semantic_scholar",
        status="hit",
        passages=passages,
        location_hints=hints,
        url=oa_pdf,
        extra={"citation_contexts_used": len(citation_passages)},
    )
