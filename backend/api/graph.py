"""Knowledge Graph API endpoints — wired to Supabase."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations import supabase_client as db

logger = logging.getLogger(__name__)
router = APIRouter()


class ConceptOut(BaseModel):
    id: str
    name: str
    type: str
    definition: str | None = None
    paper_count: int = 0
    trend: str = "stable"
    confidence: float = 0.5
    key_papers: list[dict] = []
    key_claims: list[dict] = []


class GraphNeighbors(BaseModel):
    concept: ConceptOut
    related: list[dict] = []


@router.get("/concepts", response_model=list[ConceptOut])
async def list_concepts(
    search: str | None = None,
    type: str | None = None,
    trend: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
):
    """Search/list concepts in the knowledge graph."""
    try:
        results = await db.list_concepts(
            search=search,
            type_filter=type,
            trend_filter=trend,
            limit=limit,
            offset=offset,
        )
        return [
            ConceptOut(
                id=str(c["id"]),
                name=c["name"],
                type=c.get("type", "concept"),
                definition=c.get("definition"),
                paper_count=c.get("paper_count", 0),
                trend=c.get("trend", "stable"),
                confidence=c.get("confidence", 0.5),
            )
            for c in results
        ]
    except Exception as e:
        logger.error(f"List concepts error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concepts/{concept_id}")
async def get_concept(concept_id: str):
    """Get a single concept with full context: definition, key papers, claims."""
    try:
        from backend.core.concept_enricher import get_concept_with_context

        concept = await get_concept_with_context(concept_id)
        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")
        return concept
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get concept error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concepts/{concept_id}/neighbors")
async def get_neighbors(concept_id: str, depth: int = Query(default=1, le=3)):
    """Get neighboring concepts with relationship explanations."""
    try:
        c = await db.get_concept_by_id(concept_id)
        if not c:
            raise HTTPException(status_code=404, detail="Concept not found")

        from backend.core.concept_enricher import get_enriched_neighbors

        concept = ConceptOut(
            id=str(c["id"]),
            name=c["name"],
            type=c.get("type", "concept"),
            definition=c.get("definition"),
            paper_count=c.get("paper_count", 0),
            trend=c.get("trend", "stable"),
            confidence=c.get("confidence", 0.5),
        )

        related = await get_enriched_neighbors(concept_id, depth=depth)
        return GraphNeighbors(concept=concept, related=related)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get neighbors error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def graph_stats():
    """Get knowledge graph statistics."""
    try:
        return await db.get_graph_stats()
    except Exception as e:
        logger.error(f"Graph stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
