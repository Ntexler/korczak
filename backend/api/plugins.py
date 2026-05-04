"""Plugins API — Zotero import, Anki export, Browser Extension endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Zotero ──────────────────────────────────────────────────────────────────

class ZoteroImportRequest(BaseModel):
    zotero_user_id: str
    api_key: str
    library_type: str = "users"  # "users" or "groups"
    limit: int = 100
    user_id: str = "mock-user"


@router.post("/zotero/import")
async def import_zotero(req: ZoteroImportRequest):
    """Import a Zotero library and match papers to Korczak's graph.

    Requires the user's Zotero user ID and API key.
    Returns matched papers, coverage stats, and concepts the user knows.
    """
    try:
        from backend.integrations.zotero_client import (
            fetch_zotero_library,
            match_zotero_to_korczak,
        )

        # Fetch from Zotero
        items = await fetch_zotero_library(
            user_or_group_id=req.zotero_user_id,
            api_key=req.api_key,
            library_type=req.library_type,
            limit=req.limit,
        )

        if not items:
            return {
                "status": "empty",
                "message": "No items found in Zotero library",
                "total_items": 0,
            }

        # Match to Korczak
        result = await match_zotero_to_korczak(items)

        # Update user knowledge for matched papers
        if result["matched"]:
            from backend.integrations.supabase_client import get_client
            from backend.core.attention_engine import create_signal

            client = get_client()
            for match in result["matched"]:
                # Create attention signal for each matched paper
                await create_signal(
                    user_id=req.user_id,
                    signal_type="saved_paper",
                    direction="interest",
                    target_type="paper",
                    target_id=match["korczak_paper_id"],
                    target_name=match["title"],
                    context=f"Imported from Zotero (matched by {match['match_method']})",
                )

        return {
            "status": "success",
            "total_items": result["total_items"],
            "matched": len(result["matched"]),
            "match_rate": result["match_rate"],
            "unmatched_count": result["unmatched_count"],
            "concepts_covered": result["concepts_covered"],
            "matched_papers": result["matched"][:20],  # cap response size
        }
    except Exception as e:
        logger.error(f"Zotero import error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Anki ────────────────────────────────────────────────────────────────────

@router.get("/anki/export")
async def export_anki_deck(
    field_name: str | None = None,
    concept_ids: str | None = Query(default=None, description="Comma-separated concept IDs"),
    locale: str = "en",
):
    """Export an Anki-compatible flashcard deck (TSV format).

    Import into Anki via File → Import → select the .txt file.
    """
    try:
        from backend.core.anki_exporter import generate_anki_deck

        ids = None
        if concept_ids:
            ids = [c.strip() for c in concept_ids.split(",") if c.strip()]

        if not ids and not field_name:
            raise HTTPException(status_code=400, detail="Provide field_name or concept_ids")

        result = await generate_anki_deck(
            concept_ids=ids,
            field_name=field_name,
            locale=locale,
        )

        if result["card_count"] == 0:
            raise HTTPException(status_code=404, detail="No cards generated")

        return Response(
            content=result["content"],
            media_type="text/tab-separated-values; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anki export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anki/export/json")
async def export_anki_json(
    field_name: str | None = None,
    concept_ids: str | None = Query(default=None),
    locale: str = "en",
):
    """Export Anki deck as JSON (for programmatic access)."""
    try:
        from backend.core.anki_exporter import generate_anki_deck

        ids = None
        if concept_ids:
            ids = [c.strip() for c in concept_ids.split(",") if c.strip()]

        if not ids and not field_name:
            raise HTTPException(status_code=400, detail="Provide field_name or concept_ids")

        result = await generate_anki_deck(
            concept_ids=ids,
            field_name=field_name,
            locale=locale,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anki export JSON error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Browser Extension API ──────────────────────────────────────────────────

@router.get("/extension/lookup")
async def extension_paper_lookup(
    doi: str | None = None,
    title: str | None = None,
    url: str | None = None,
):
    """Browser extension endpoint: look up a paper by DOI or title.

    Returns Korczak's knowledge about this paper:
    - Whether it's in the graph
    - Related concepts
    - Claims and their evidence status
    - Connections to other papers
    """
    if not doi and not title:
        raise HTTPException(status_code=400, detail="Provide doi or title")

    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()

        paper = None

        # Try DOI first
        if doi:
            result = client.table("papers").select(
                "id, title, authors, publication_year, cited_by_count, doi, abstract, subfield"
            ).eq("doi", doi).execute()
            if result.data:
                paper = result.data[0]

        # Try title match
        if not paper and title:
            result = client.table("papers").select(
                "id, title, authors, publication_year, cited_by_count, doi, abstract, subfield"
            ).ilike("title", f"%{title[:80]}%").limit(1).execute()
            if result.data:
                paper = result.data[0]

        if not paper:
            return {
                "found": False,
                "message": "Paper not in Korczak's knowledge graph yet",
                "suggestion": "Upload it to Korczak to add it to the graph",
            }

        # Get concepts
        pc = client.table("paper_concepts").select(
            "concept_id, relevance"
        ).eq("paper_id", paper["id"]).order("relevance", desc=True).limit(10).execute()

        concepts = []
        if pc.data:
            concept_ids = [r["concept_id"] for r in pc.data]
            c_result = client.table("concepts").select(
                "id, name, type, confidence"
            ).in_("id", concept_ids).execute()
            concepts = c_result.data or []

        # Get claims
        claims = client.table("claims").select(
            "claim_text, evidence_type, strength, confidence"
        ).eq("paper_id", paper["id"]).order("confidence", desc=True).limit(5).execute()

        return {
            "found": True,
            "paper": {
                "id": paper["id"],
                "title": paper["title"],
                "year": paper.get("publication_year"),
                "cited_by": paper.get("cited_by_count", 0),
                "field": paper.get("subfield", ""),
            },
            "concepts": [
                {"name": c["name"], "type": c.get("type"), "confidence": c.get("confidence", 0)}
                for c in concepts
            ],
            "claims": claims.data or [],
            "concept_count": len(concepts),
            "claim_count": len(claims.data or []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extension lookup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extension/signal")
async def extension_create_signal(
    user_id: str = Query(default="mock-user"),
    paper_doi: str | None = None,
    paper_title: str | None = None,
    direction: str = Query(default="interest"),
):
    """Browser extension: flag a paper for attention (interest or skepticism)."""
    try:
        from backend.core.attention_engine import create_signal

        target_name = paper_title or paper_doi or "Unknown paper"
        signal = await create_signal(
            user_id=user_id,
            signal_type="flagged",
            direction=direction,
            target_type="paper",
            target_id=paper_doi,
            target_name=target_name,
            context=f"Flagged via browser extension ({direction})",
        )
        return signal
    except Exception as e:
        logger.error(f"Extension signal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Multi-Source Search ─────────────────────────────────────────────────────

@router.get("/search/multi")
async def multi_source_paper_search(
    query: str = Query(..., min_length=2),
    limit: int = Query(default=5, le=20),
    sources: str | None = Query(default=None, description="Comma-separated: semantic_scholar,crossref,europe_pmc,core"),
    year_from: int | None = None,
):
    """Search 4+ academic databases in parallel. Returns deduplicated results."""
    try:
        from backend.integrations.multi_source_search import multi_source_search

        source_list = [s.strip() for s in sources.split(",")] if sources else None
        result = await multi_source_search(
            query=query,
            limit_per_source=limit,
            sources=source_list,
            year_from=year_from,
        )
        return result
    except Exception as e:
        logger.error(f"Multi-source search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── SciCrunch RRID ──────────────────────────────────────────────────────────

@router.get("/scicrunch/lookup/{rrid}")
async def lookup_rrid(rrid: str):
    """Look up a Research Resource Identifier (RRID)."""
    try:
        from backend.integrations.scicrunch_client import lookup_rrid as _lookup
        result = await _lookup(rrid)
        if not result:
            raise HTTPException(status_code=404, detail="RRID not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RRID lookup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scicrunch/search")
async def search_research_resources(
    query: str = Query(..., min_length=2),
    category: str | None = None,
    limit: int = Query(default=10, le=20),
):
    """Search for research resources (antibodies, software, cell lines, etc.)."""
    try:
        from backend.integrations.scicrunch_client import search_resources
        results = await search_resources(query=query, category=category, limit=limit)
        return {"resources": results, "total": len(results)}
    except Exception as e:
        logger.error(f"SciCrunch search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Sci-Bot Bridge ─────────────────────────────────────────────────────────

@router.get("/scibot/query")
async def query_scibot_endpoint(
    question: str = Query(..., min_length=5),
):
    """Query Sci-Bot for full-text-grounded answers.

    Currently returns a redirect URL (Sci-Bot has no API yet).
    When API becomes available, will return direct answers with references.
    """
    try:
        from backend.integrations.scibot_bridge import query_scibot
        result = await query_scibot(question)
        return result
    except Exception as e:
        logger.error(f"Sci-Bot query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scibot/url")
async def get_scibot_redirect_url(
    question: str = Query(..., min_length=5),
):
    """Get a direct URL to Sci-Bot with a pre-filled question."""
    from backend.integrations.scibot_bridge import get_scibot_url
    return {"url": get_scibot_url(question), "source": "scibot"}


# ─── Author Investigation ───────────────────────────────────────────────────

@router.get("/author/investigate")
async def investigate_author(
    name: str | None = None,
    openalex_id: str | None = None,
):
    """Full investigation of an author: profile, credibility, retractions."""
    if not name and not openalex_id:
        raise HTTPException(status_code=400, detail="Provide name or openalex_id")
    try:
        from backend.agents.author_investigator import full_investigation
        result = await full_investigation(
            author_name=name or "",
            openalex_id=openalex_id,
        )
        return result
    except Exception as e:
        logger.error(f"Author investigation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
