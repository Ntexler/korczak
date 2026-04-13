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
from backend.core.concept_enricher import get_personal_overlay, get_simple_explanation

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
    include_lens_data: bool = Query(default=False),
):
    """Get nodes and edges for D3.js graph visualization (with definitions + explanations).
    Set include_lens_data=true for controversy/recency/community/gap lens metadata."""
    try:
        from backend.core.concept_enricher import get_enriched_graph_data
        return await get_enriched_graph_data(limit=limit, include_lens_data=include_lens_data)
    except Exception as e:
        logger.error(f"Graph visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visualization/geographic")
async def geographic_visualization():
    """Get institution locations with paper counts for geographic map visualization."""
    try:
        from backend.core.concept_enricher import get_geographic_data
        return await get_geographic_data()
    except Exception as e:
        logger.error(f"Geographic visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visualization/sankey")
async def sankey_visualization():
    """Get relationship flow data between concept types for Sankey diagram."""
    try:
        from backend.core.concept_enricher import get_sankey_flow_data
        return await get_sankey_flow_data()
    except Exception as e:
        logger.error(f"Sankey visualization error: {e}", exc_info=True)
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


@router.get("/overlay/{user_id}")
async def personal_knowledge_overlay(
    user_id: str,
    limit: int = Query(default=100, le=500),
):
    """Get personal knowledge overlay — fog of war data for the graph.

    Returns each concept's status: explored (green), in_progress (amber), unexplored (fog).
    """
    try:
        result = await get_personal_overlay(user_id, limit)
        return result
    except Exception as e:
        logger.error(f"Overlay error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{concept_id}")
async def explain_concept(concept_id: str, locale: str = "en"):
    """Get a simple, TA-level explanation of a concept."""
    try:
        result = await get_simple_explanation(concept_id, locale)
        if not result:
            raise HTTPException(status_code=404, detail="Concept not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explain error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Fields API ---

@router.get("/fields")
async def list_fields():
    """List all knowledge fields with stats (paper count, concept count, top concepts)."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    try:
        # Get all unique subfields from papers, grouped as fields
        papers = client.table("papers").select("subfield").not_.is_("subfield", "null").execute()

        # Group papers by field
        field_counts: dict[str, int] = {}
        for p in (papers.data or []):
            field = _normalize_field(p.get("subfield", ""))
            if field:
                field_counts[field] = field_counts.get(field, 0) + 1

        # Get concept counts per type (as proxy for field richness)
        concepts = client.table("concepts").select("type", count="exact").execute()

        # Get generated courses per department
        courses = client.table("generated_courses").select(
            "department, level"
        ).eq("is_published", True).execute()
        course_counts: dict[str, int] = {}
        for c in (courses.data or []):
            dept = c.get("department", "")
            course_counts[dept] = course_counts.get(dept, 0) + 1

        # Build field list
        fields = []
        for field, paper_count in sorted(field_counts.items(), key=lambda x: -x[1]):
            fields.append({
                "name": field,
                "paper_count": paper_count,
                "course_count": course_counts.get(field, 0),
            })

        # Only return core fields (clean, no duplicates/noise)
        # Add core fields that have no papers yet (from syllabi)
        existing_fields = {f["name"] for f in fields}
        for core_field in CORE_FIELDS:
            if core_field not in existing_fields:
                fields.append({
                    "name": core_field,
                    "paper_count": 0,
                    "course_count": course_counts.get(core_field, 0),
                })

        # Filter to only core fields and sort by paper count
        fields = [f for f in fields if f["name"] in CORE_FIELDS]
        fields.sort(key=lambda x: -x["paper_count"])

        return {"fields": fields, "total": len(fields)}
    except Exception as e:
        logger.error(f"Fields error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fields/{field_name}/syllabus")
async def get_field_syllabus(field_name: str, level: str = "intro"):
    """Get the syllabus/course structure for a field.

    Returns week-by-week structure with concepts and readings.
    """
    from backend.integrations.supabase_client import get_client
    client = get_client()

    try:
        # Try generated course first
        course = client.table("generated_courses").select("*").eq(
            "department", field_name
        ).eq("level", level).eq("is_published", True).limit(1).execute()

        if course.data:
            c = course.data[0]
            readings = client.table("course_readings").select("*").eq(
                "course_id", c["id"]
            ).order("week").order("position").execute()
            c["readings"] = readings.data
            return c

        # Fallback: get concepts for this field, ordered by paper_count
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence"
        ).order("paper_count", desc=True).limit(50).execute()

        # Organize into a basic syllabus structure
        weeks = []
        items = concepts.data or []
        for i in range(0, len(items), 3):
            week_items = items[i:i+3]
            weeks.append({
                "week_number": (i // 3) + 1,
                "title": f"Week {(i // 3) + 1}",
                "concepts": [
                    {"id": c["id"], "name": c["name"], "type": c["type"],
                     "definition": c.get("definition", ""), "paper_count": c.get("paper_count", 0)}
                    for c in week_items
                ],
            })

        return {
            "department": field_name,
            "level": level,
            "title": f"{field_name} — {level.title()} Track",
            "weeks": weeks,
            "is_generated": False,
            "note": "Auto-organized by paper count. Generated courses coming soon.",
        }
    except Exception as e:
        logger.error(f"Field syllabus error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fields/{field_name}/concepts")
async def get_field_concepts(
    field_name: str,
    limit: int = Query(default=50, le=200),
):
    """Get concepts for a specific field, with simple explanations."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    try:
        # Search concepts that match the field
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence, trend, controversy_score"
        ).order("paper_count", desc=True).limit(limit).execute()

        return {"field": field_name, "concepts": concepts.data, "total": len(concepts.data or [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_field(subfield: str) -> str:
    """Map paper subfields to broader field names."""
    if not subfield:
        return ""
    s = subfield.lower()
    mappings = {
        "anthropol": "Anthropology", "ethnograph": "Anthropology", "ethnomusicol": "Anthropology",
        "archaeol": "Anthropology", "decoloni": "Anthropology", "indigenous": "Anthropology",
        "settler": "Anthropology", "postcoloni": "Anthropology",
        "sleep": "Sleep & Cognition", "circadian": "Sleep & Cognition", "wakefulness": "Sleep & Cognition",
        "cogniti": "Cognitive Science", "consciousness": "Cognitive Science",
        "psychol": "Psychology", "psychomet": "Psychology", "psycho-": "Psychology",
        "sociol": "Sociology", "social theory": "Sociology", "social science": "Sociology",
        "econom": "Economics", "consumer": "Economics",
        "politi": "Political Science", "international relation": "Political Science", "governance": "Political Science",
        "philosoph": "Philosophy", "phenomenol": "Philosophy", "critical theory": "Philosophy",
        "linguist": "Linguistics", "communication": "Linguistics",
        "histor": "History", "memory stud": "History", "heritage": "History", "slavery": "History",
        "biolog": "Biology", "ecology": "Biology", "ecosystem": "Biology", "genetic": "Biology",
        "neurosci": "Neuroscience", "neuroph": "Neuroscience", "neuroimag": "Neuroscience",
        "neurodegen": "Neuroscience", "hippocamp": "Neuroscience", "neuroplast": "Neuroscience",
        "physic": "Physics", "atmospheric": "Climate Science", "climate": "Climate Science",
        "meteorol": "Climate Science", "ocean": "Climate Science", "hydrolog": "Climate Science",
        "mathemat": "Mathematics", "statistic": "Mathematics", "computational": "Mathematics",
        "computer": "Computer Science", "digital": "Computer Science", "data stud": "Computer Science",
        "geograph": "Geography", "urban": "Geography", "spatial": "Geography", "migration": "Geography",
        "medical": "Medicine", "clinical": "Medicine", "nephrol": "Medicine", "cardiol": "Medicine",
        "oncol": "Medicine", "hematol": "Medicine", "surg": "Medicine", "nurs": "Medicine",
        "epidemiol": "Medicine", "hospital": "Medicine", "pharma": "Medicine", "anesthes": "Medicine",
        "perioper": "Medicine", "pain med": "Medicine", "infect": "Medicine", "diagnos": "Medicine",
        "dermatol": "Medicine", "pediatr": "Medicine", "geriatr": "Medicine", "psychiatr": "Medicine",
        "emergen": "Medicine", "integrative med": "Medicine", "critical care": "Medicine",
        "vascular": "Medicine", "biomedic": "Medicine", "health": "Medicine",
        "gender": "Gender Studies", "feminist": "Gender Studies", "queer": "Gender Studies", "women": "Gender Studies",
        "religio": "Religious Studies", "theolog": "Religious Studies",
        "legal": "Law", "law": "Law", "justice": "Law", "criminal": "Law",
        "education": "Education",
        "environment": "Environmental Science", "conservation": "Environmental Science",
        "media": "Media Studies", "visual": "Media Studies", "museum": "Media Studies",
        "tourism": "Cultural Studies", "cultural stud": "Cultural Studies", "food": "Cultural Studies",
        "african": "Area Studies", "asian": "Area Studies", "island": "Area Studies",
        "management": "Business", "organization": "Business", "marketing": "Business",
        "development": "Development Studies", "humanitarian": "Development Studies",
    }
    for key, field in mappings.items():
        if key in s:
            return field
    return ""  # Don't show unmapped subfields — they add noise


CORE_FIELDS = [
    "Anthropology", "Sleep & Cognition", "Cognitive Science", "Psychology",
    "Sociology", "Economics", "Political Science", "Philosophy", "Linguistics",
    "History", "Biology", "Neuroscience", "Physics", "Mathematics",
    "Computer Science", "Geography", "Medicine", "Climate Science",
    "Gender Studies", "Religious Studies", "Law", "Education",
    "Environmental Science", "Media Studies", "Cultural Studies",
    "Area Studies", "Business", "Development Studies",
]
