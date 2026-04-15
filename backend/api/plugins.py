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
