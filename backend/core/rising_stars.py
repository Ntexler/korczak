"""Rising Stars Tracker — detects concepts and papers with abnormal growth.

Identifies:
  - Concepts appearing in many recent papers (trending topics)
  - Papers with rapidly growing citation counts
  - New concepts that emerged recently but already have strong connections
  - Authors publishing frequently on emerging topics
"""

import logging
from datetime import datetime, timedelta, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def get_trending_concepts(days: int = 90, limit: int = 15) -> list[dict]:
    """Find concepts that appear in the most recent papers.

    A concept is 'trending' if it shows up disproportionately in recent papers
    compared to older ones.
    """
    client = get_client()
    cutoff_year = datetime.now(timezone.utc).year - max(days // 365, 1)

    # Get recent papers by publication year
    recent_papers = (
        client.table("papers")
        .select("id")
        .gte("publication_year", cutoff_year)
        .execute()
    )
    recent_ids = {p["id"] for p in recent_papers.data}

    if not recent_ids:
        # Fallback: use last N papers by creation date
        recent_papers = (
            client.table("papers")
            .select("id")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        recent_ids = {p["id"] for p in recent_papers.data}

    # Get paper-concept links for recent papers
    paper_concepts = (
        client.table("paper_concepts")
        .select("paper_id, concept_id")
        .execute()
    )

    # Count concept appearances in recent vs all papers
    recent_counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for pc in paper_concepts.data:
        cid = pc["concept_id"]
        total_counts[cid] = total_counts.get(cid, 0) + 1
        if pc["paper_id"] in recent_ids:
            recent_counts[cid] = recent_counts.get(cid, 0) + 1

    # Score: recent appearances weighted more heavily
    scored = []
    for cid, recent in recent_counts.items():
        total = total_counts.get(cid, 1)
        # Score combines recency ratio and volume
        recency_ratio = recent / max(total, 1)
        score = recent * (1 + recency_ratio)
        scored.append({
            "concept_id": cid,
            "recent_papers": recent,
            "total_papers": total,
            "recency_ratio": round(recency_ratio, 2),
            "trend_score": round(score, 2),
        })

    scored.sort(key=lambda x: -x["trend_score"])
    top = scored[:limit]

    # Enrich with concept names
    if top:
        concept_ids = [t["concept_id"] for t in top]
        concepts = (
            client.table("concepts")
            .select("id, name, type, definition")
            .in_("id", concept_ids)
            .execute()
        )
        name_map = {c["id"]: c for c in concepts.data}
        for t in top:
            info = name_map.get(t["concept_id"], {})
            t["name"] = info.get("name", "Unknown")
            t["type"] = info.get("type", "concept")
            t["definition"] = info.get("definition")

    return top


async def get_rising_papers(days: int = 180, limit: int = 15) -> list[dict]:
    """Find papers with high citation counts relative to their age.

    Young papers with high citations are 'rising stars'.
    """
    client = get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get recent-ish papers with citation data
    papers = (
        client.table("papers")
        .select("id, title, authors, publication_year, cited_by_count, created_at")
        .gte("created_at", cutoff)
        .order("cited_by_count", desc=True)
        .limit(100)
        .execute()
    )

    results = []
    now = datetime.now(timezone.utc)
    for p in papers.data:
        citations = p.get("cited_by_count") or 0
        if citations == 0:
            continue

        # Calculate age in days from publication_year (integer) or created_at
        pub_year = p.get("publication_year")
        if pub_year and isinstance(pub_year, int):
            age_days = max((now.year - pub_year) * 365, 1)
        else:
            created_at = p.get("created_at", "")
            try:
                if isinstance(created_at, str) and created_at:
                    age_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = max((now - age_date).days, 1)
                else:
                    age_days = 365
            except (ValueError, TypeError):
                age_days = 365

        # Citations per day (velocity)
        velocity = citations / age_days

        results.append({
            "paper_id": p["id"],
            "title": p["title"],
            "authors": p.get("authors"),
            "publication_year": p.get("publication_year"),
            "cited_by_count": citations,
            "age_days": age_days,
            "citation_velocity": round(velocity, 4),
        })

    results.sort(key=lambda x: -x["citation_velocity"])
    return results[:limit]


async def get_emerging_connections(days: int = 90, limit: int = 15) -> list[dict]:
    """Find recently created relationships — new connections in the graph."""
    client = get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    relationships = (
        client.table("relationships")
        .select("id, source_id, target_id, relationship_type, confidence, created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    if not relationships.data:
        # Fallback: just get most recent relationships
        relationships = (
            client.table("relationships")
            .select("id, source_id, target_id, relationship_type, confidence, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    # Enrich with concept names
    concept_ids = set()
    for r in relationships.data:
        concept_ids.add(r["source_id"])
        concept_ids.add(r["target_id"])

    if concept_ids:
        concepts = (
            client.table("concepts")
            .select("id, name")
            .in_("id", list(concept_ids))
            .execute()
        )
        name_map = {c["id"]: c["name"] for c in concepts.data}
    else:
        name_map = {}

    results = []
    for r in relationships.data:
        results.append({
            "relationship_id": r["id"],
            "source_name": name_map.get(r["source_id"], "Unknown"),
            "target_name": name_map.get(r["target_id"], "Unknown"),
            "relationship_type": r["relationship_type"],
            "confidence": r.get("confidence", 0.5),
            "created_at": r.get("created_at"),
        })

    return results


async def get_rising_stars_report(days: int = 90, limit: int = 10) -> dict:
    """Full rising stars report combining trending concepts, papers, and connections."""
    concepts = await get_trending_concepts(days=days, limit=limit)
    papers = await get_rising_papers(days=days * 2, limit=limit)
    connections = await get_emerging_connections(days=days, limit=limit)

    return {
        "period_days": days,
        "trending_concepts": concepts,
        "rising_papers": papers,
        "emerging_connections": connections,
        "summary": {
            "trending_concepts": len(concepts),
            "rising_papers": len(papers),
            "emerging_connections": len(connections),
        },
    }
