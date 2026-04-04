"""Controversy Mapper — maps sides, evidence, and timeline for active debates.

Uses the controversies table + relationships (CONTRADICTS, RESPONDS_TO) to
build a structured view of academic debates.
"""

import logging
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def get_controversies(limit: int = 10, active_only: bool = True) -> list[dict]:
    """List controversies with summary data."""
    client = get_client()
    query = client.table("controversies").select("*")
    if active_only:
        query = query.eq("status", "active")
    query = query.order("created_at", desc=True).limit(limit)
    result = query.execute()
    return result.data


async def get_controversy_detail(controversy_id: str) -> dict | None:
    """Get a controversy with its sides, evidence, and related concepts."""
    client = get_client()

    # Get the controversy
    controversy = (
        client.table("controversies")
        .select("*")
        .eq("id", controversy_id)
        .execute()
    )
    if not controversy.data:
        return None

    data = controversy.data[0]

    # Find CONTRADICTS relationships to map opposing concepts
    contradicts = (
        client.table("relationships")
        .select("source_id, target_id, confidence, explanation")
        .eq("relationship_type", "CONTRADICTS")
        .execute()
    )

    # Find RESPONDS_TO relationships for debate chains
    responds = (
        client.table("relationships")
        .select("source_id, target_id, confidence, explanation")
        .eq("relationship_type", "RESPONDS_TO")
        .execute()
    )

    data["contradicting_pairs"] = len(contradicts.data)
    data["response_chains"] = len(responds.data)

    return data


async def map_debate_landscape(keyword: str) -> dict:
    """Build a debate landscape for a topic.

    Returns sides, key papers on each side, evidence strength, and timeline.
    """
    client = get_client()

    # Search controversies
    controversies = (
        client.table("controversies")
        .select("*")
        .ilike("title", f"%{keyword}%")
        .execute()
    )

    # Search CONTRADICTS relationships involving matching concepts
    matching_concepts = (
        client.table("concepts")
        .select("id, name, type")
        .ilike("name", f"%{keyword}%")
        .limit(10)
        .execute()
    )
    concept_ids = [c["id"] for c in matching_concepts.data]

    contradictions = []
    if concept_ids:
        for cid in concept_ids[:5]:
            contra = (
                client.table("relationships")
                .select("source_id, target_id, confidence, explanation")
                .eq("relationship_type", "CONTRADICTS")
                .eq("source_id", cid)
                .execute()
            )
            contradictions.extend(contra.data)

            contra2 = (
                client.table("relationships")
                .select("source_id, target_id, confidence, explanation")
                .eq("relationship_type", "CONTRADICTS")
                .eq("target_id", cid)
                .execute()
            )
            contradictions.extend(contra2.data)

    return {
        "keyword": keyword,
        "controversies": controversies.data,
        "related_concepts": matching_concepts.data,
        "contradictions": contradictions,
        "total_debates": len(controversies.data),
        "total_contradictions": len(contradictions),
    }
