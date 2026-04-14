"""Claim-level API endpoints (Feature 6.5).

Routes (mounted at /api/claims by main.py):
  GET  /{claim_id}                     — full claim row + paper + authors
  GET  /{claim_id}/provenance          — cached provenance record (no side effects)
  POST /{claim_id}/extract-provenance  — run the multi-source extractor, persist,
                                          return the fresh or cached result
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.access_resolver import summarize_for_ui
from backend.core.author_enricher import ensure_author_profile
from backend.core.provenance import extract_claim_provenance
from backend.integrations.supabase_client import get_client


logger = logging.getLogger(__name__)
router = APIRouter()


# -------------------- models --------------------


class ExampleModel(BaseModel):
    text: str
    kind: str | None = None
    location: str | None = None


class AuthorLite(BaseModel):
    name: str
    openalex_id: str | None = None
    orcid: str | None = None
    institution: str | None = None
    country: str | None = None
    profile_id: str | None = None
    bio: str | None = None


class PaperLite(BaseModel):
    id: str
    title: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    access_url: str | None = None
    access_status: str | None = None
    access_ui: dict | None = None
    authors: list[AuthorLite] = []
    funding: list[dict] = []


class ClaimResponse(BaseModel):
    id: str
    claim_text: str
    evidence_type: str | None = None
    strength: str | None = None
    confidence: float | None = None
    testable: bool | None = None
    # Provenance (may be null until extractor runs)
    verbatim_quote: str | None = None
    quote_location: str | None = None
    claim_category: str | None = None
    examples: list[ExampleModel] = []
    provenance_sources: list[dict] = []
    provenance_extracted_at: str | None = None
    # Source paper (denormalized for convenience)
    paper: PaperLite


class ProvenanceResponse(BaseModel):
    claim_id: str
    verbatim_quote: str | None
    quote_location: str | None
    claim_category: str | None
    examples: list[ExampleModel]
    provenance_sources: list[dict]
    extracted_at: str | None
    cached: bool


# -------------------- helpers --------------------


def _augment_paper(paper: dict | None) -> dict | None:
    if not paper:
        return None
    access_status = paper.get("access_status")
    if access_status:
        paper["access_ui"] = summarize_for_ui(access_status)
    return paper


def _augment_authors(authors: list[dict]) -> list[dict]:
    """Attach author_profiles.id + bio (if available) to each author record.

    Does NOT trigger enrichment — just a lookup. Triggering expensive OpenAlex
    + Claude work on every claim fetch would be too slow; the backfill job and
    the dedicated authors endpoint handle enrichment.
    """
    if not authors:
        return []

    client = get_client()
    openalex_ids = [a.get("openalex_id") for a in authors if a.get("openalex_id")]
    profiles_by_openalex: dict[str, dict] = {}
    if openalex_ids:
        try:
            result = (
                client.table("author_profiles")
                .select("id, openalex_id, name, bio, country, primary_institution, primary_field")
                .in_("openalex_id", openalex_ids)
                .execute()
            )
            for p in result.data or []:
                if p.get("openalex_id"):
                    profiles_by_openalex[p["openalex_id"]] = p
        except Exception as e:
            logger.warning(f"Author profile lookup failed: {e}")

    augmented = []
    for a in authors:
        profile = profiles_by_openalex.get(a.get("openalex_id") or "")
        augmented.append({
            "name": a.get("name"),
            "openalex_id": a.get("openalex_id"),
            "orcid": a.get("orcid"),
            "institution": a.get("institution") or (profile or {}).get("primary_institution"),
            "country": a.get("country") or (profile or {}).get("country"),
            "profile_id": (profile or {}).get("id"),
            "bio": (profile or {}).get("bio"),
        })
    return augmented


# -------------------- routes --------------------


@router.get("/{claim_id}")
async def get_claim(claim_id: str):
    """Return a claim with all Feature 6.5 provenance fields + paper + authors."""
    client = get_client()
    try:
        result = (
            client.table("claims")
            .select(
                "id, claim_text, evidence_type, strength, confidence, testable, "
                "verbatim_quote, quote_location, claim_category, examples, "
                "provenance_sources, provenance_extracted_at, "
                "papers(id, title, publication_year, doi, access_url, access_status, "
                "authors, funding)"
            )
            .eq("id", claim_id)
            .execute()
        )
    except Exception as e:
        logger.error(f"get_claim error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    if not result.data:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim = result.data[0]
    paper_raw = claim.pop("papers", None)
    paper = _augment_paper(paper_raw or {})
    authors = _augment_authors((paper or {}).get("authors") or [])

    return {
        "id": claim["id"],
        "claim_text": claim["claim_text"],
        "evidence_type": claim.get("evidence_type"),
        "strength": claim.get("strength"),
        "confidence": claim.get("confidence"),
        "testable": claim.get("testable"),
        "verbatim_quote": claim.get("verbatim_quote"),
        "quote_location": claim.get("quote_location"),
        "claim_category": claim.get("claim_category"),
        "examples": claim.get("examples") or [],
        "provenance_sources": claim.get("provenance_sources") or [],
        "provenance_extracted_at": claim.get("provenance_extracted_at"),
        "paper": {
            "id": (paper or {}).get("id"),
            "title": (paper or {}).get("title"),
            "publication_year": (paper or {}).get("publication_year"),
            "doi": (paper or {}).get("doi"),
            "access_url": (paper or {}).get("access_url"),
            "access_status": (paper or {}).get("access_status"),
            "access_ui": (paper or {}).get("access_ui"),
            "authors": authors,
            "funding": (paper or {}).get("funding") or [],
        },
    }


@router.get("/{claim_id}/provenance")
async def get_provenance(claim_id: str):
    """Return the cached provenance record for a claim (does not trigger extraction)."""
    client = get_client()
    result = (
        client.table("claims")
        .select(
            "id, verbatim_quote, quote_location, claim_category, examples, "
            "provenance_sources, provenance_extracted_at"
        )
        .eq("id", claim_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Claim not found")
    row = result.data[0]
    return {
        "claim_id": row["id"],
        "verbatim_quote": row.get("verbatim_quote"),
        "quote_location": row.get("quote_location"),
        "claim_category": row.get("claim_category"),
        "examples": row.get("examples") or [],
        "provenance_sources": row.get("provenance_sources") or [],
        "extracted_at": row.get("provenance_extracted_at"),
        "cached": row.get("provenance_extracted_at") is not None,
    }


class ExtractRequest(BaseModel):
    force: bool = False


@router.post("/{claim_id}/extract-provenance")
async def extract_provenance(claim_id: str, req: ExtractRequest | None = None):
    """Run the multi-source extractor. Idempotent — re-use cached result unless force=true."""
    force = bool(req.force) if req else False
    try:
        result = await extract_claim_provenance(claim_id, force=force)
    except Exception as e:
        logger.error(f"extract_provenance error for {claim_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Extraction failed")
    if result is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {
        "claim_id": result.claim_id,
        "verbatim_quote": result.verbatim_quote,
        "quote_location": result.quote_location,
        "claim_category": result.claim_category,
        "examples": result.examples,
        "provenance_sources": result.provenance_sources,
        "extracted_at": result.extracted_at,
        "cached": result.cached,
    }
