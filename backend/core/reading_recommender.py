"""Smart reading recommendations based on user's saved papers and interests."""

import logging
from collections import Counter

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Weights for save_context — higher = stronger interest signal
CONTEXT_WEIGHTS = {
    "browsing": 1.0,
    "chat_reference": 0.8,
    "recommendation": 0.6,
    "syllabus": 0.5,
    "search_result": 0.3,
}


async def build_interest_profile(user_id: str) -> dict[str, float]:
    """Build a weighted concept interest profile from saved papers.

    Returns {concept_name: weight} where weight reflects genuine interest.
    """
    client = get_client()

    # Get user's saved papers with context
    saved = (
        client.table("user_papers")
        .select("paper_id, save_context, status, rating")
        .eq("user_id", user_id)
        .execute()
    )
    if not saved.data:
        return {}

    paper_ids = [row["paper_id"] for row in saved.data]
    paper_contexts = {row["paper_id"]: row for row in saved.data}

    # Get concepts linked to these papers
    paper_concepts = (
        client.table("paper_concepts")
        .select("paper_id, concept_id, relevance, concepts(id, name)")
        .in_("paper_id", paper_ids)
        .execute()
    )

    # Weight concepts by save_context, relevance, and frequency
    concept_scores: Counter = Counter()
    concept_names: dict[str, str] = {}

    for pc in paper_concepts.data:
        concept = pc.get("concepts")
        if not concept:
            continue
        cid = concept["id"]
        concept_names[cid] = concept["name"]

        paper_info = paper_contexts.get(pc["paper_id"], {})
        context_weight = CONTEXT_WEIGHTS.get(paper_info.get("save_context", "browsing"), 0.5)
        relevance = pc.get("relevance", 0.5) or 0.5

        # Boost for completed/rated papers
        status_boost = 1.3 if paper_info.get("status") == "completed" else 1.0
        rating_boost = 1.0 + (paper_info.get("rating") or 3) * 0.1

        score = context_weight * relevance * status_boost * rating_boost
        concept_scores[cid] += score

    # Normalize and return as {concept_name: weight}
    if not concept_scores:
        return {}

    max_score = max(concept_scores.values())
    return {
        concept_names[cid]: round(score / max_score, 2)
        for cid, score in concept_scores.most_common(20)
    }


async def get_recommendations(user_id: str, limit: int = 10) -> list[dict]:
    """Get paper recommendations based on user's interest profile.

    Returns papers the user hasn't saved that share concepts with their high-interest areas.
    """
    client = get_client()

    # Get user's saved paper IDs
    saved = (
        client.table("user_papers")
        .select("paper_id")
        .eq("user_id", user_id)
        .execute()
    )
    saved_paper_ids = {row["paper_id"] for row in (saved.data or [])}

    if not saved_paper_ids:
        # New user — recommend most-cited papers
        popular = (
            client.table("papers")
            .select("id, title, authors, publication_year, cited_by_count, abstract")
            .order("cited_by_count", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            {**p, "reason": "Highly cited in the knowledge graph"}
            for p in (popular.data or [])
        ]

    # Build interest profile
    profile = await build_interest_profile(user_id)
    if not profile:
        return []

    # Get concept IDs for top interests
    top_concept_names = list(profile.keys())[:10]
    concepts = (
        client.table("concepts")
        .select("id, name")
        .in_("name", top_concept_names)
        .execute()
    )
    concept_id_to_name = {c["id"]: c["name"] for c in (concepts.data or [])}
    concept_ids = list(concept_id_to_name.keys())

    if not concept_ids:
        return []

    # Find papers sharing these concepts that user hasn't saved
    paper_concepts = (
        client.table("paper_concepts")
        .select("paper_id, concept_id, relevance")
        .in_("concept_id", concept_ids)
        .order("relevance", desc=True)
        .limit(200)
        .execute()
    )

    # Score unsaved papers
    paper_scores: Counter = Counter()
    paper_reasons: dict[str, list[str]] = {}

    for pc in (paper_concepts.data or []):
        pid = pc["paper_id"]
        if pid in saved_paper_ids:
            continue
        cid = pc["concept_id"]
        cname = concept_id_to_name.get(cid, "")
        weight = profile.get(cname, 0.5)
        relevance = pc.get("relevance", 0.5) or 0.5
        paper_scores[pid] += weight * relevance
        if cname:
            paper_reasons.setdefault(pid, []).append(cname)

    if not paper_scores:
        return []

    # Fetch top papers
    top_paper_ids = [pid for pid, _ in paper_scores.most_common(limit)]
    papers = (
        client.table("papers")
        .select("id, title, authors, publication_year, cited_by_count, abstract")
        .in_("id", top_paper_ids)
        .execute()
    )

    paper_map = {p["id"]: p for p in (papers.data or [])}
    results = []
    for pid, score in paper_scores.most_common(limit):
        paper = paper_map.get(pid)
        if not paper:
            continue
        reasons = paper_reasons.get(pid, [])[:3]
        reason_text = f"Because you saved papers about {', '.join(reasons)}" if reasons else "Related to your interests"
        results.append({**paper, "reason": reason_text, "score": round(score, 2)})

    return results
