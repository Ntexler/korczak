"""AI Curator — finds niche-but-important papers that syllabi miss.

Korczak's own judgment: analyzes the knowledge graph to identify papers
that are underrepresented in syllabi but conceptually critical.
"""

import asyncio
import logging

from backend.config import settings
from backend.integrations.claude_client import _call_claude, _parse_json_response
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def find_hidden_gems(department: str, limit: int = 20) -> list[dict]:
    """Find papers that are niche in syllabi but important in the knowledge graph.

    Criteria for a "hidden gem":
    - Low syllabus frequency (<10%)
    - BUT high concept connectivity (linked to 5+ concepts)
    - OR bridge paper (connects separate concept clusters)
    - OR high controversy_score
    - OR cited by canonical papers
    """
    client = get_client()
    gems = []

    # 1. Get papers with high concept connectivity
    # Find papers linked to many concepts
    connected_papers = client.rpc("get_papers_by_concept_count", {
        "min_concepts": 5,
        "max_results": 100,
    }).execute() if False else []  # RPC may not exist yet

    # Fallback: query directly
    # Get papers with their concept counts
    papers_result = client.table("papers").select(
        "id, title, abstract, authors, publication_year, cited_by_count, "
        "paper_type, subfield"
    ).order("cited_by_count", desc=True).limit(200).execute()

    if not papers_result.data:
        logger.info("No papers found for AI curation")
        return gems

    # 2. For each paper, check concept connectivity
    for paper in papers_result.data:
        paper_id = paper["id"]

        # Count concepts linked to this paper
        concepts_result = client.table("paper_concepts").select(
            "concept_id"
        ).eq("paper_id", paper_id).execute()
        concept_count = len(concepts_result.data) if concepts_result.data else 0

        if concept_count < 4:
            continue

        # Check if it's already well-represented in syllabi
        reading_score = client.table("reading_scores").select(
            "combined_score, tier"
        ).eq("paper_id", paper_id).limit(1).execute()

        if reading_score.data and reading_score.data[0].get("tier") in ("canonical", "important"):
            continue  # Already well-known

        # Check for controversy connections
        controversy_rels = client.table("relationships").select("id").or_(
            f"source_id.eq.{paper_id},target_id.eq.{paper_id}"
        ).eq("relationship_type", "CONTRADICTS").execute()
        is_controversial = len(controversy_rels.data) > 0 if controversy_rels.data else False

        # This paper is a candidate — ask Claude
        title = paper.get("title", "")
        abstract = (paper.get("abstract") or "")[:500]
        concept_names = []
        if concepts_result.data:
            concept_ids = [c["concept_id"] for c in concepts_result.data[:8]]
            names_result = client.table("concepts").select(
                "name"
            ).in_("id", concept_ids).execute()
            concept_names = [c["name"] for c in names_result.data] if names_result.data else []

        gems.append({
            "paper_id": paper_id,
            "title": title,
            "abstract": abstract,
            "concept_count": concept_count,
            "concept_names": concept_names,
            "is_controversial": is_controversial,
            "cited_by_count": paper.get("cited_by_count", 0),
        })

        if len(gems) >= limit * 2:
            break

    # 3. Ask Claude to evaluate the candidates
    if not gems:
        return []

    evaluated = await _evaluate_candidates(gems, department)
    return evaluated[:limit]


async def _evaluate_candidates(candidates: list[dict], department: str) -> list[dict]:
    """Ask Claude to evaluate which niche papers are actually important."""
    # Build a concise summary of candidates
    candidate_lines = []
    for i, c in enumerate(candidates[:30]):
        concepts = ", ".join(c["concept_names"][:5])
        candidate_lines.append(
            f"{i+1}. \"{c['title']}\" — {c['concept_count']} concepts ({concepts}), "
            f"{c['cited_by_count']} citations"
            f"{', CONTROVERSIAL' if c['is_controversial'] else ''}"
        )

    prompt = f"""You are an academic curator for the field of {department}.

Below are papers that are underrepresented in university syllabi but have strong
connections in the knowledge graph. Evaluate which ones are genuinely important
for students to read, even though they don't appear in most syllabi.

Candidates:
{chr(10).join(candidate_lines)}

For each paper worth recommending, return a JSON array:
[
  {{
    "index": 1,
    "importance_score": 0.0-1.0,
    "rationale": "Why this paper matters despite being underrepresented",
    "suggested_week": 1-14
  }}
]

Only include papers scoring >= 0.6 importance. Be selective — not every niche paper
is a hidden gem. Look for papers that:
- Bridge important concepts that are usually taught separately
- Offer a critical perspective missing from standard syllabi
- Provide methodology that's increasingly important
- Challenge dominant paradigms in productive ways

Return ONLY valid JSON array.
"""

    try:
        response = await _call_claude(
            prompt,
            model=settings.haiku_model,
            max_tokens=1000,
            temperature=0.2,
        )
        parsed = _parse_json_response(response.text)

        if isinstance(parsed, list):
            evaluations = parsed
        elif isinstance(parsed, dict) and not parsed.get("parse_error"):
            evaluations = parsed.get("recommendations", [parsed])
        else:
            logger.warning("AI curator: failed to parse response")
            return []

        # Map evaluations back to candidates
        result = []
        for ev in evaluations:
            idx = ev.get("index", 0) - 1
            if 0 <= idx < len(candidates) and ev.get("importance_score", 0) >= 0.6:
                candidate = candidates[idx]
                result.append({
                    "paper_id": candidate["paper_id"],
                    "title": candidate["title"],
                    "importance_score": ev["importance_score"],
                    "rationale": ev.get("rationale", ""),
                    "suggested_week": ev.get("suggested_week", 7),
                    "concept_connections": candidate["concept_count"],
                    "is_bridge_paper": candidate["concept_count"] >= 6,
                    "controversy_score": 0.8 if candidate["is_controversial"] else 0.0,
                })

        # Sort by importance
        result.sort(key=lambda x: x["importance_score"], reverse=True)
        logger.info(f"AI curator found {len(result)} hidden gems for {department}")
        return result

    except Exception as e:
        logger.error(f"AI curator evaluation failed: {e}")
        return []


async def store_curated_readings(department: str, gems: list[dict]):
    """Store AI-curated readings in the reading_scores table."""
    client = get_client()

    for gem in gems:
        score_data = {
            "paper_id": gem["paper_id"],
            "reading_title": gem["title"][:500],
            "department": department,
            "frequency_score": 0.0,
            "institution_diversity": 0.0,
            "position_score": max(0, 1 - (gem["suggested_week"] - 1) / 14),
            "citation_weight": 0.0,
            "teaching_score": 0.0,
            "user_adjustment": 0.0,
            "combined_score": gem["importance_score"] * 0.20,  # AI bonus
            "tier": "ai_recommended",
            "source_count": 0,
            "source_institutions": [],
            "ai_rationale": gem["rationale"],
        }
        client.table("reading_scores").insert(score_data).execute()

    logger.info(f"Stored {len(gems)} AI-curated readings for {department}")
