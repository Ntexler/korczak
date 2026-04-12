"""Knowledge Timeline API — track how knowledge evolves over time."""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/concept/{concept_id}")
async def concept_timeline(
    concept_id: str,
    limit: int = Query(default=50, le=200),
):
    """Get the evolution history of a concept."""
    try:
        client = get_client()

        # Get concept info
        concept = client.table("concepts").select("id, name, type, definition, confidence, created_at").eq("id", concept_id).execute()
        if not concept.data:
            raise HTTPException(status_code=404, detail="Concept not found")

        # Get history snapshots
        history = (
            client.table("concept_history")
            .select("*")
            .eq("concept_id", concept_id)
            .order("recorded_at")
            .limit(limit)
            .execute()
        )

        # Get related papers sorted by year
        papers = (
            client.table("paper_concepts")
            .select("papers(id, title, publication_year, cited_by_count)")
            .eq("concept_id", concept_id)
            .execute()
        )
        paper_timeline = sorted(
            [p["papers"] for p in (papers.data or []) if p.get("papers") and p["papers"].get("publication_year")],
            key=lambda p: p["publication_year"],
        )

        return {
            "concept": concept.data[0],
            "history": history.data or [],
            "paper_timeline": paper_timeline,
            "first_appearance": paper_timeline[0]["publication_year"] if paper_timeline else None,
            "latest_paper": paper_timeline[-1]["publication_year"] if paper_timeline else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Concept timeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/field")
async def field_timeline(
    year_start: int = Query(default=1950),
    year_end: int = Query(default=2026),
):
    """Get a timeline of the field's evolution: concept emergence by year."""
    try:
        client = get_client()

        # Get papers grouped by year
        papers = (
            client.table("papers")
            .select("publication_year, id")
            .gte("publication_year", year_start)
            .lte("publication_year", year_end)
            .execute()
        )

        # Count papers per year
        year_counts: dict[int, int] = {}
        for p in (papers.data or []):
            yr = p.get("publication_year")
            if yr:
                year_counts[yr] = year_counts.get(yr, 0) + 1

        # Get milestones
        milestones = (
            client.table("field_milestones")
            .select("*")
            .gte("year", year_start)
            .lte("year", year_end)
            .order("year")
            .execute()
        )

        # Get concepts with their first appearance (based on earliest paper)
        concept_emergence = (
            client.table("concepts")
            .select("id, name, type, created_at")
            .order("created_at")
            .execute()
        )

        return {
            "papers_by_year": [
                {"year": yr, "count": count}
                for yr, count in sorted(year_counts.items())
            ],
            "milestones": milestones.data or [],
            "concepts_emerged": len(concept_emergence.data or []),
            "year_range": {"start": year_start, "end": year_end},
        }
    except Exception as e:
        logger.error(f"Field timeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fields")
async def list_fields():
    """Get all distinct concept types (fields) for filtering."""
    try:
        client = get_client()
        result = client.table("concepts").select("type").execute()
        types: dict[str, int] = {}
        for row in (result.data or []):
            t = row.get("type", "concept")
            types[t] = types.get(t, 0) + 1
        fields = [{"type": t, "count": c} for t, c in sorted(types.items(), key=lambda x: -x[1])]
        return {"fields": fields}
    except Exception as e:
        logger.error(f"List fields error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concept-type")
async def concept_type_timeline(
    concept_type: str = Query(...),
    year_start: int = Query(default=1950),
    year_end: int = Query(default=2026),
):
    """Get timeline data filtered by concept type (field)."""
    try:
        client = get_client()

        # Get concepts of this type
        concepts = (
            client.table("concepts")
            .select("id, name, type, confidence, paper_count")
            .eq("type", concept_type)
            .order("confidence", desc=True)
            .execute()
        )
        concept_ids = [c["id"] for c in (concepts.data or [])]

        # Get papers linked to these concepts
        year_counts: dict[int, int] = {}
        top_papers_by_year: dict[int, list] = {}
        if concept_ids:
            paper_links = (
                client.table("paper_concepts")
                .select("papers(id, title, publication_year, cited_by_count, authors)")
                .in_("concept_id", concept_ids[:200])
                .execute()
            )
            seen_papers: set[str] = set()
            for link in (paper_links.data or []):
                p = link.get("papers")
                if not p or not p.get("publication_year"):
                    continue
                pid = p["id"]
                yr = p["publication_year"]
                if yr < year_start or yr > year_end:
                    continue
                if pid not in seen_papers:
                    seen_papers.add(pid)
                    year_counts[yr] = year_counts.get(yr, 0) + 1
                    if yr not in top_papers_by_year:
                        top_papers_by_year[yr] = []
                    if len(top_papers_by_year[yr]) < 3:
                        top_papers_by_year[yr].append({
                            "title": p.get("title", ""),
                            "cited_by_count": p.get("cited_by_count", 0),
                            "authors": (p.get("authors") or [])[:2],
                        })

        return {
            "concept_type": concept_type,
            "concept_count": len(concepts.data or []),
            "papers_by_year": [
                {"year": yr, "count": count}
                for yr, count in sorted(year_counts.items())
            ],
            "top_papers_by_year": {str(yr): papers for yr, papers in top_papers_by_year.items()},
            "top_concepts": [
                {"id": c["id"], "name": c["name"], "confidence": c["confidence"], "paper_count": c.get("paper_count", 0)}
                for c in (concepts.data or [])[:10]
            ],
        }
    except Exception as e:
        logger.error(f"Concept type timeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changelog")
async def graph_changelog(
    limit: int = Query(default=50, le=200),
    change_type: str | None = None,
):
    """Get the changelog of all graph modifications."""
    try:
        client = get_client()
        query = (
            client.table("graph_changelog")
            .select("*")
            .order("recorded_at", desc=True)
            .limit(limit)
        )
        if change_type:
            query = query.eq("change_type", change_type)

        result = query.execute()
        return {"changes": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error(f"Changelog error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/milestones")
async def list_milestones(
    milestone_type: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """Get field milestones (paradigm shifts, breakthroughs, etc.)."""
    try:
        client = get_client()
        query = (
            client.table("field_milestones")
            .select("*")
            .order("year", desc=True)
            .limit(limit)
        )
        if milestone_type:
            query = query.eq("milestone_type", milestone_type)

        result = query.execute()
        return {"milestones": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error(f"Milestones error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
