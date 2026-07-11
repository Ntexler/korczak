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


@router.get("/concepts/{concept_id}/evidence-trail")
async def evidence_trail(concept_id: str):
    """'How do I know this?' — the full evidence chain behind a concept.

    Returns: claims → the papers asserting them → citation edges among
    those papers → Chappie deep-dive journeys that walked this concept.
    Epistemic transparency: every belief traceable to its sources.
    """
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()

        concept = client.table("concepts").select(
            "id, name, definition, consensus_status, consensus_score, definition_source"
        ).eq("id", concept_id).execute()
        if not concept.data:
            raise HTTPException(status_code=404, detail="Concept not found")
        c = concept.data[0]

        # Papers behind the concept (with relevance)
        pc = client.table("paper_concepts").select(
            "paper_id, relevance"
        ).eq("concept_id", concept_id).order("relevance", desc=True).limit(10).execute()
        paper_ids = [r["paper_id"] for r in (pc.data or [])]
        relevance = {r["paper_id"]: r.get("relevance") for r in (pc.data or [])}

        papers = []
        for i in range(0, len(paper_ids), 40):
            rows = client.table("papers").select(
                "id, title, publication_year, doi, cited_by_count"
            ).in_("id", paper_ids[i:i + 40]).execute()
            papers.extend(rows.data or [])
        for p in papers:
            p["relevance"] = relevance.get(p["id"])

        # Claims those papers assert
        claims = []
        if paper_ids:
            from backend.integrations.supabase_client import get_claims_for_papers
            claims = await get_claims_for_papers([str(pid) for pid in paper_ids], limit=10)

        # Citation edges AMONG these papers (who builds on whom)
        citations = []
        if paper_ids:
            id_set = set(paper_ids)
            rels = client.table("relationships").select(
                "source_id, target_id"
            ).eq("relationship_type", "CITES").in_("source_id", paper_ids).execute()
            title_by_id = {p["id"]: p["title"] for p in papers}
            for r in (rels.data or []):
                if r["target_id"] in id_set:
                    citations.append({
                        "from": title_by_id.get(r["source_id"], r["source_id"]),
                        "to": title_by_id.get(r["target_id"], r["target_id"]),
                    })

        # Chappie journeys that walked this concept
        journeys = client.table("chappie_journeys").select(
            "id, synthesis, hops, papers_read, consensus_found, contested_found, created_at"
        ).ilike("start_concept", f"%{c['name']}%").order(
            "created_at", desc=True
        ).limit(3).execute()

        return {
            "concept": c,
            "papers": papers,
            "claims": claims,
            "citations_among_papers": citations,
            "chappie_journeys": journeys.data or [],
            "trail_summary": {
                "papers": len(papers),
                "claims": len(claims),
                "internal_citations": len(citations),
                "deep_dives": len(journeys.data or []),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Evidence trail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revisions")
async def belief_revisions(field: str | None = None, limit: int = 20):
    """Public: Korczak's changes of mind — the intellectual biography.

    A teaching artifact: changing your mind on evidence is an achievement.
    """
    from backend.agents.belief_memory import get_revisions
    return {"revisions": await get_revisions(field=field, limit=min(limit, 50))}


@router.get("/concepts/{concept_id}/revisions")
async def concept_revision_history(concept_id: str):
    """The full 'how my understanding of this evolved' story for one concept."""
    from backend.agents.belief_memory import get_subject_history
    return {"history": await get_subject_history(concept_id)}


@router.get("/failures")
async def knowledge_failures(field: str | None = None, limit: int = 20):
    """The memory of failure — how knowledge went wrong before.

    Phlogiston, N-rays, the replication crisis. A system that remembers
    how knowledge broke in the past recognizes it breaking in the present.
    """
    from backend.integrations.supabase_client import get_client
    client = get_client()
    q = client.table("knowledge_failures").select("*")
    if field:
        q = q.eq("field", field)
    rows = q.order("created_at", desc=True).limit(min(limit, 50)).execute()
    return {"failures": rows.data or []}


@router.get("/concepts/{concept_id}/cautionary")
async def cautionary_tales(concept_id: str):
    """Relevant 'here's how similar ideas went wrong' warnings for a concept.

    Matches the concept's name/field against known knowledge failures —
    a knowledge vaccine: shows learners the failure modes of the neighborhood.
    """
    from backend.integrations.supabase_client import get_client
    client = get_client()
    c = client.table("concepts").select("name, field_span").eq("id", concept_id).execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="Concept not found")
    fields = c.data[0].get("field_span") or []

    failures = client.table("knowledge_failures").select("*").execute()
    relevant = []
    for f in (failures.data or []):
        if f.get("field") in fields or any(
            f.get("field", "").lower() in fld.lower() for fld in fields
        ):
            relevant.append(f)
    return {"concept": c.data[0]["name"], "cautionary_tales": relevant[:5]}
