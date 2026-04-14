"""Author profile API (Feature 6.5).

Routes (mounted at /api/authors by main.py):
  GET  /profile/{profile_id}            — full author_profiles row
  GET  /profile/by-openalex/{openalex_id} — lookup/stub/enrich on first access
  GET  /profile/{profile_id}/papers     — papers this author contributed to
  POST /profile/{profile_id}/enrich     — force-refresh enrichment + bio
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.core.author_enricher import (
    ensure_author_profile,
    enrich_from_openalex,
    generate_bio,
)
from backend.integrations.supabase_client import get_client


logger = logging.getLogger(__name__)
router = APIRouter()


def _find_papers_for_author(openalex_id: str | None, name: str | None, limit: int) -> list[dict]:
    """Find papers whose authors[] array references this author.

    We match on openalex_id first (preferred) and fall back to name.
    Supabase JSONB containment uses the `cs` operator for `@>`.
    """
    if not (openalex_id or name):
        return []
    client = get_client()

    # Prefer openalex_id match — stable across renames / typos.
    if openalex_id:
        try:
            result = (
                client.table("papers")
                .select("id, title, publication_year, cited_by_count, doi, access_status, access_url")
                .filter("authors", "cs", f'[{{"openalex_id":"{openalex_id}"}}]')
                .order("cited_by_count", desc=True)
                .limit(limit)
                .execute()
            )
            if result.data:
                return result.data
        except Exception as e:
            logger.warning(f"Papers-by-author openalex match failed: {e}")

    if name:
        try:
            result = (
                client.table("papers")
                .select("id, title, publication_year, cited_by_count, doi, access_status, access_url")
                .filter("authors", "cs", f'[{{"name":"{name}"}}]')
                .order("cited_by_count", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"Papers-by-author name match failed: {e}")

    return []


@router.get("/profile/{profile_id}")
async def get_profile(profile_id: str):
    """Return a single author profile by id."""
    client = get_client()
    result = client.table("author_profiles").select("*").eq("id", profile_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Author profile not found")
    return result.data[0]


@router.get("/profile/by-openalex/{openalex_id}")
async def get_profile_by_openalex(openalex_id: str, auto_enrich: bool = Query(default=True)):
    """Return the author_profiles row for an OpenAlex ID.

    If the row doesn't exist, a stub is created. If `auto_enrich=true` and the
    stub is un-enriched, we enrich from OpenAlex and generate a bio inline
    (so the first viewer pays a small latency cost; subsequent viewers see
    cached data immediately).
    """
    profile = ensure_author_profile(openalex_id=openalex_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Could not resolve author")

    if auto_enrich and profile.get("enriched_at") is None:
        try:
            profile = await enrich_from_openalex(profile) or profile
        except Exception as e:
            logger.warning(f"Inline enrichment failed for {openalex_id}: {e}")
        if profile.get("enriched_at") and not profile.get("bio"):
            try:
                profile = await generate_bio(profile) or profile
            except Exception as e:
                logger.warning(f"Inline bio generation failed for {openalex_id}: {e}")

    return profile


@router.get("/profile/{profile_id}/papers")
async def get_profile_papers(profile_id: str, limit: int = Query(default=20, le=100)):
    """Return papers this author contributed to (highest-cited first)."""
    client = get_client()
    result = client.table("author_profiles").select("openalex_id, name").eq("id", profile_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Author profile not found")
    row = result.data[0]
    papers = _find_papers_for_author(row.get("openalex_id"), row.get("name"), limit)
    return {"papers": papers, "total": len(papers)}


@router.post("/profile/{profile_id}/enrich")
async def force_enrich(profile_id: str):
    """Force-refresh enrichment + bio regardless of cache state."""
    client = get_client()
    result = client.table("author_profiles").select("*").eq("id", profile_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Author profile not found")
    profile = result.data[0]

    try:
        profile = await enrich_from_openalex(profile) or profile
    except Exception as e:
        logger.error(f"Force enrich failed: {e}")
        raise HTTPException(status_code=502, detail="OpenAlex enrichment failed")

    try:
        profile = await generate_bio(profile) or profile
    except Exception as e:
        logger.warning(f"Bio generation failed (enrichment still applied): {e}")

    return profile
