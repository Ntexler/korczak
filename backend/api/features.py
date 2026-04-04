"""Features API — controversies, white space, rising stars, briefings."""

import logging

from fastapi import APIRouter, Query

from backend.core.controversy_mapper import (
    get_controversies,
    get_controversy_detail,
    map_debate_landscape,
)
from backend.core.white_space_finder import find_research_gaps
from backend.core.rising_stars import get_rising_stars_report
from backend.core.briefing_engine import generate_briefing, get_briefing_topics

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Controversies ---

@router.get("/controversies")
async def list_controversies(
    limit: int = Query(default=10, le=50),
    active_only: bool = True,
):
    """List active controversies in the knowledge graph."""
    return await get_controversies(limit=limit, active_only=active_only)


@router.get("/controversies/{controversy_id}")
async def controversy_detail(controversy_id: str):
    """Get detailed controversy with sides and evidence."""
    result = await get_controversy_detail(controversy_id)
    if result is None:
        return {"error": "Controversy not found"}
    return result


@router.get("/debates")
async def debate_landscape(keyword: str = Query(..., min_length=2)):
    """Map the debate landscape for a topic."""
    return await map_debate_landscape(keyword)


# --- White Space / Research Gaps ---

@router.get("/gaps")
async def research_gaps(
    keyword: str | None = None,
    limit: int = Query(default=20, le=50),
):
    """Find research gaps: orphan concepts, missing connections, low-evidence debates."""
    return await find_research_gaps(keyword=keyword, limit=limit)


# --- Rising Stars ---

@router.get("/rising")
async def rising_stars(
    days: int = Query(default=90, le=365),
    limit: int = Query(default=10, le=50),
):
    """Get trending concepts, rising papers, and emerging connections."""
    return await get_rising_stars_report(days=days, limit=limit)


# --- Briefings ---

@router.get("/briefing")
async def briefing(
    user_id: str | None = None,
    briefing_type: str = Query(default="daily", pattern="^(daily|weekly|deep_dive)$"),
):
    """Generate a personalized briefing (data + prompt, requires Claude for full text)."""
    return await generate_briefing(user_id=user_id, briefing_type=briefing_type)


@router.get("/briefing/topics")
async def briefing_topics(user_id: str | None = None):
    """Get personalized topic suggestions for exploration."""
    return await get_briefing_topics(user_id=user_id)


# --- Graph Visualization Data ---

@router.get("/visualization/graph")
async def graph_visualization_data(
    limit: int = Query(default=100, le=500),
):
    """Get nodes and edges for D3.js force-directed graph visualization."""
    from backend.integrations.supabase_client import get_client

    client = get_client()

    # Get concepts as nodes
    concepts = (
        client.table("concepts")
        .select("id, name, type, confidence")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    concept_ids = {c["id"] for c in concepts.data}

    # Get relationships as edges (only between included concepts)
    relationships = (
        client.table("relationships")
        .select("id, source_id, target_id, relationship_type, confidence")
        .execute()
    )

    # Filter edges to only include nodes we have
    edges = [
        {
            "id": r["id"],
            "source": r["source_id"],
            "target": r["target_id"],
            "type": r["relationship_type"],
            "confidence": r.get("confidence", 0.5),
        }
        for r in relationships.data
        if r["source_id"] in concept_ids and r["target_id"] in concept_ids
    ]

    # Map concept types to colors for the frontend
    type_colors = {
        "theory": "#E8B931",       # gold
        "method": "#58A6FF",       # blue
        "concept": "#3FB950",      # green
        "finding": "#D29922",      # amber
        "person": "#BC8CFF",       # purple
        "institution": "#F78166",  # orange
    }

    nodes = [
        {
            "id": c["id"],
            "name": c["name"],
            "type": c.get("type", "concept"),
            "confidence": c.get("confidence", 0.5),
            "color": type_colors.get(c.get("type", "concept"), "#8B949E"),
        }
        for c in concepts.data
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
