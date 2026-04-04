"""Briefing Engine — generates personalized knowledge briefings.

Combines user profile + rising stars + research gaps + controversies
to build a "what you should know" briefing for each user.

Briefing modes:
  - daily: Quick highlights (trending concepts, new papers in your area)
  - weekly: Deeper analysis (gaps, controversies, connections you missed)
  - deep_dive: Full analysis of a specific topic with personalized angle
"""

import logging
from backend.integrations.supabase_client import get_client
from backend.core.rising_stars import get_trending_concepts, get_rising_papers
from backend.core.white_space_finder import find_research_gaps
from backend.core.controversy_mapper import get_controversies
from backend.user.context_extractor import get_rich_user_context

logger = logging.getLogger(__name__)

BRIEFING_PROMPT = """You are Korczak — a knowledge navigator preparing a personalized briefing.

ABOUT THE USER:
{user_context}

BRIEFING DATA:
{briefing_data}

Generate a {briefing_type} briefing that:
1. Highlights what's most relevant to THIS user based on their profile
2. Connects trending topics to their research interests
3. Points out gaps they might want to explore
4. Mentions any active controversies in their area
5. Suggests one unexpected connection they haven't considered

FORMAT:
- Use warm, engaging tone (you're a colleague sharing exciting news)
- Lead with the most important item for THIS user
- Keep daily briefings to 3-5 bullet points
- Weekly briefings can have sections with headers
- Always end with a thought-provoking question or suggestion
- Respond in the user's preferred language (default: English)"""


async def build_briefing_data(user_id: str | None = None) -> dict:
    """Gather all data needed for a briefing."""
    trending = await get_trending_concepts(days=30, limit=5)
    rising = await get_rising_papers(days=90, limit=5)
    gaps = await find_research_gaps(limit=5)
    controversies = await get_controversies(limit=5, active_only=True)

    return {
        "trending_concepts": trending,
        "rising_papers": rising,
        "research_gaps": gaps.get("summary", {}),
        "active_controversies": controversies,
    }


def format_briefing_data(data: dict) -> str:
    """Format briefing data as readable text for the LLM prompt."""
    parts = []

    # Trending concepts
    if data.get("trending_concepts"):
        parts.append("TRENDING CONCEPTS:")
        for c in data["trending_concepts"][:5]:
            parts.append(f"  - {c.get('name', 'Unknown')} (type: {c.get('type', 'concept')}, "
                        f"recent papers: {c.get('recent_papers', 0)}, "
                        f"trend score: {c.get('trend_score', 0)})")

    # Rising papers
    if data.get("rising_papers"):
        parts.append("\nRISING PAPERS:")
        for p in data["rising_papers"][:5]:
            parts.append(f"  - \"{p.get('title', 'Untitled')}\" "
                        f"(citations: {p.get('citation_count', 0)}, "
                        f"velocity: {p.get('citation_velocity', 0)}/day)")

    # Research gaps
    if data.get("research_gaps"):
        gaps = data["research_gaps"]
        parts.append(f"\nRESEARCH GAPS: {gaps.get('total_gaps', 0)} identified "
                    f"({gaps.get('orphan_concepts', 0)} orphan concepts, "
                    f"{gaps.get('missing_connections', 0)} missing connections)")

    # Controversies
    if data.get("active_controversies"):
        parts.append("\nACTIVE CONTROVERSIES:")
        for c in data["active_controversies"][:5]:
            parts.append(f"  - {c.get('title', 'Untitled')}")

    return "\n".join(parts) if parts else "No notable updates found."


async def generate_briefing(
    user_id: str | None = None,
    briefing_type: str = "daily",
) -> dict:
    """Generate a personalized briefing.

    Returns the briefing prompt and data (actual generation requires Claude API).
    """
    # Get user context
    if user_id:
        user_context = await get_rich_user_context(user_id)
    else:
        user_context = "Anonymous user — general academic audience."

    # Build data
    data = await build_briefing_data(user_id)
    formatted = format_briefing_data(data)

    # Build prompt (to be sent to Claude when credits available)
    prompt = BRIEFING_PROMPT.format(
        user_context=user_context,
        briefing_data=formatted,
        briefing_type=briefing_type,
    )

    return {
        "briefing_type": briefing_type,
        "user_id": user_id,
        "prompt": prompt,
        "raw_data": data,
        "formatted_data": formatted,
        "status": "ready_for_generation",  # Will be "generated" when Claude processes it
    }


async def get_briefing_topics(user_id: str | None = None) -> list[dict]:
    """Get personalized topic suggestions for the user.

    These are topics the user should explore based on their profile
    and current graph state — no LLM needed.
    """
    trending = await get_trending_concepts(days=60, limit=10)

    # If we have a user, filter for relevance
    suggestions = []
    for c in trending:
        suggestions.append({
            "topic": c.get("name", "Unknown"),
            "type": c.get("type", "concept"),
            "reason": f"Trending: {c.get('recent_papers', 0)} recent papers, "
                     f"score {c.get('trend_score', 0)}",
            "trend_score": c.get("trend_score", 0),
        })

    return suggestions
