"""Provenance extraction orchestrator (Feature 6.5, Stage C).

Given a `claim_id`, fetches the claim + its paper, runs all sources in
parallel, calls the aggregator, and persists the result.

Idempotent: if `claims.provenance_extracted_at` is already populated, the
orchestrator returns the cached record without any network or LLM calls.
"""

import asyncio
import logging
from datetime import datetime, timezone

from backend.core.provenance.aggregator import aggregate
from backend.core.provenance.sources import (
    arxiv as src_arxiv,
    core_api as src_core,
    full_text as src_full_text,
    semantic_scholar as src_s2,
    unpaywall as src_unpaywall,
)
from backend.core.provenance.types import (
    ExtractionContext,
    ExtractionResult,
    SourceResult,
)
from backend.integrations.supabase_client import get_client


logger = logging.getLogger(__name__)


# Source modules in the order they'll be shown in diagnostics.
_SOURCES = [
    src_full_text,
    src_unpaywall,
    src_s2,
    src_core,
    src_arxiv,
]


async def _run_sources(ctx: ExtractionContext) -> list[SourceResult]:
    """Run every source concurrently, swallowing unexpected exceptions."""

    async def _safe(module) -> SourceResult:
        try:
            return await module.fetch(ctx)
        except Exception as e:
            name = module.__name__.rsplit(".", 1)[-1]
            logger.warning(f"Source {name} raised: {e}")
            # Use the module name as source; won't match SourceName typing exactly
            # for unknown modules, but our own modules are consistent.
            return SourceResult(source=name, status="error", error=str(e))  # type: ignore[arg-type]

    return await asyncio.gather(*[_safe(m) for m in _SOURCES])


async def extract_claim_provenance(claim_id: str, *, force: bool = False) -> ExtractionResult | None:
    """Run the extraction for a single claim. Returns cached result if present.

    Args:
        claim_id: UUID of the claim row.
        force: if True, re-extract even if `provenance_extracted_at` is set.
    Returns:
        ExtractionResult, or None if the claim wasn't found.
    """
    client = get_client()

    claim_rows = (
        client.table("claims")
        .select(
            "id, claim_text, paper_id, verbatim_quote, quote_location, "
            "claim_category, examples, provenance_sources, provenance_extracted_at, "
            "papers(id, title, doi, publication_year, full_text, full_text_source)"
        )
        .eq("id", claim_id)
        .execute()
    )
    if not claim_rows.data:
        return None

    claim = claim_rows.data[0]
    paper = claim.pop("papers", None) or {}

    # Cache hit — return what's already in the DB without hitting the network.
    if not force and claim.get("provenance_extracted_at"):
        return ExtractionResult(
            claim_id=claim_id,
            verbatim_quote=claim.get("verbatim_quote"),
            quote_location=claim.get("quote_location"),
            claim_category=claim.get("claim_category"),
            examples=claim.get("examples") or [],
            provenance_sources=claim.get("provenance_sources") or [],
            extracted_at=claim["provenance_extracted_at"],
            cached=True,
        )

    ctx = ExtractionContext(
        claim_id=claim_id,
        claim_text=claim["claim_text"],
        paper_id=paper.get("id") or claim.get("paper_id"),
        doi=paper.get("doi"),
        title=paper.get("title") or "",
        full_text=paper.get("full_text"),
        full_text_source=paper.get("full_text_source"),
    )

    source_results = await _run_sources(ctx)
    aggregated = await aggregate(ctx, source_results, year=paper.get("publication_year"))

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "verbatim_quote": aggregated["verbatim_quote"],
        "quote_location": aggregated["quote_location"],
        "claim_category": aggregated["claim_category"],
        "examples": aggregated["examples"],
        "provenance_sources": aggregated["provenance_sources"],
        "provenance_extracted_at": now_iso,
    }
    try:
        client.table("claims").update(update).eq("id", claim_id).execute()
    except Exception as e:
        logger.warning(f"Persist extraction for claim {claim_id} failed: {e}")
        # Still return the extracted data in-memory so the UI can render it.

    return ExtractionResult(
        claim_id=claim_id,
        verbatim_quote=aggregated["verbatim_quote"],
        quote_location=aggregated["quote_location"],
        claim_category=aggregated["claim_category"],
        examples=aggregated["examples"],
        provenance_sources=aggregated["provenance_sources"],
        extracted_at=now_iso,
        cached=False,
    )
