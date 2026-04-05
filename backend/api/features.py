"""Features API — controversies, white space, rising stars, briefings, knowledge tree."""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.core.controversy_mapper import (
    get_controversies,
    get_controversy_detail,
    map_debate_landscape,
)
from backend.core.white_space_finder import find_research_gaps
from backend.core.rising_stars import get_rising_stars_report
from backend.core.briefing_engine import generate_briefing, get_briefing_topics
from backend.user.behavior_tracker import get_engagement_profile

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Controversies ---

@router.get("/controversies")
async def list_controversies(
    limit: int = Query(default=10, le=50),
    active_only: bool = True,
):
    """List active controversies in the knowledge graph."""
    try:
        return await get_controversies(limit=limit, active_only=active_only)
    except Exception as e:
        logger.error(f"Controversies error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/controversies/{controversy_id}")
async def controversy_detail(controversy_id: str):
    """Get detailed controversy with sides and evidence."""
    try:
        result = await get_controversy_detail(controversy_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Controversy not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Controversy detail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debates")
async def debate_landscape(keyword: str = Query(..., min_length=2)):
    """Map the debate landscape for a topic."""
    try:
        return await map_debate_landscape(keyword)
    except Exception as e:
        logger.error(f"Debate landscape error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- White Space / Research Gaps ---

@router.get("/gaps")
async def research_gaps(
    keyword: str | None = None,
    limit: int = Query(default=20, le=50),
):
    """Find research gaps: orphan concepts, missing connections, low-evidence debates."""
    try:
        return await find_research_gaps(keyword=keyword, limit=limit)
    except Exception as e:
        logger.error(f"Research gaps error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Rising Stars ---

@router.get("/rising")
async def rising_stars(
    days: int = Query(default=90, le=365),
    limit: int = Query(default=10, le=50),
):
    """Get trending concepts, rising papers, and emerging connections."""
    try:
        return await get_rising_stars_report(days=days, limit=limit)
    except Exception as e:
        logger.error(f"Rising stars error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Briefings ---

@router.get("/briefing")
async def briefing(
    user_id: str | None = None,
    briefing_type: str = Query(default="daily", pattern="^(daily|weekly|deep_dive)$"),
):
    """Generate a personalized briefing (data + prompt, requires Claude for full text)."""
    try:
        return await generate_briefing(user_id=user_id, briefing_type=briefing_type)
    except Exception as e:
        logger.error(f"Briefing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/briefing/topics")
async def briefing_topics(user_id: str | None = None):
    """Get personalized topic suggestions for exploration."""
    try:
        return await get_briefing_topics(user_id=user_id)
    except Exception as e:
        logger.error(f"Briefing topics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- User Engagement ---

@router.get("/engagement/{user_id}")
async def user_engagement(user_id: str):
    """Get engagement profile for a user (behavioral patterns, learning velocity)."""
    try:
        return await get_engagement_profile(user_id)
    except Exception as e:
        logger.error(f"Engagement profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Graph Visualization Data ---

@router.get("/visualization/graph")
async def graph_visualization_data(
    limit: int = Query(default=100, le=500),
):
    """Get nodes and edges for D3.js force-directed graph visualization."""
    try:
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
    except Exception as e:
        logger.error(f"Graph visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Knowledge Tree ---

@router.get("/tree")
async def knowledge_tree(
    user_id: str = Query(...),
    domain: str | None = None,
):
    """Get user's knowledge tree (nodes + edges + statuses)."""
    try:
        from backend.core.knowledge_tree import build_user_tree
        return await build_user_tree(user_id, root_domain=domain)
    except Exception as e:
        logger.error(f"Knowledge tree error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tree/choose")
async def choose_tree_branch(
    user_id: str = Query(...),
    branch_point_id: str = Query(...),
    chosen_concept_id: str = Query(...),
):
    """Choose a branch at a fork in the knowledge tree."""
    try:
        from backend.core.knowledge_tree import choose_branch
        return await choose_branch(user_id, branch_point_id, chosen_concept_id)
    except Exception as e:
        logger.error(f"Branch choice error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree/branches")
async def tree_branches(
    concept_id: str = Query(...),
    user_id: str = Query(...),
):
    """Get available branches at a concept (fork point)."""
    try:
        from backend.core.knowledge_tree import get_available_branches
        return {"branches": await get_available_branches(user_id, concept_id)}
    except Exception as e:
        logger.error(f"Tree branches error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree/progress")
async def tree_progress(user_id: str = Query(...)):
    """Get knowledge tree progress summary."""
    try:
        from backend.core.knowledge_tree import get_tree_progress
        return await get_tree_progress(user_id)
    except Exception as e:
        logger.error(f"Tree progress error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visualization/progress")
async def visualization_progress(
    user_id: str = Query(...),
    syllabus_id: str | None = None,
):
    """Enhanced graph with centrality, user_level, is_pillar for progress visualization."""
    try:
        from backend.core.centrality import compute_concept_centrality, classify_pillar_vs_niche
        from backend.integrations.supabase_client import get_client

        client = get_client()

        # Get user knowledge
        user_knowledge = (
            client.table("user_knowledge")
            .select("concept_id, understanding_level")
            .eq("user_id", user_id)
            .execute()
        )
        knowledge_map = {
            uk["concept_id"]: uk["understanding_level"]
            for uk in (user_knowledge.data or [])
        }

        # Get centrality and pillar classification
        centrality = await compute_concept_centrality()
        pillars = await classify_pillar_vs_niche()

        nodes = []
        for cid, data in centrality.items():
            nodes.append({
                "id": cid,
                "name": data["name"],
                "type": data["type"],
                "centrality": round(data["centrality"], 3),
                "is_pillar": pillars.get(cid) == "pillar",
                "classification": pillars.get(cid, "standard"),
                "user_level": knowledge_map.get(cid, 0),
            })

        return {"nodes": nodes, "total": len(nodes)}
    except Exception as e:
        logger.error(f"Progress visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
