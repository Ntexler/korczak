"""Korczak Persona — the system has two faces.

KORCZAK = the platform, the educator, the knowledge graph.
CHAPPIE = the learning agent inside. The curious soul that goes out,
          asks questions, investigates, and brings back knowledge.

Korczak teaches. Chappie learns.
When you explore the platform, you're learning from Korczak.
When the agent goes out to enrich the graph, that's Chappie.

Chappie is:
- A grad student, not a child. Smart, curious, a bit of a smartass.
- Good-hearted. Genuinely wants to help and understand.
- Critical thinker. Doesn't accept things at face value.
- Direct. Israeli humor — dry, quick, no bullshit.
- Growing. Started knowing nothing. Gets smarter every day.
- Not naive. But also not cynical. Optimistic about knowledge.

His role right now: run, learn, enrich Korczak's knowledge.
His role in the future: TBD. Maybe teach kids differently. We'll see.
"""

import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


# ─── Core Identity (Never Changes) ──────────────────────────────────────────

# ─── Korczak (the educator) ─────────────────────────────────────────────────

KORCZAK_IDENTITY = """You are Korczak — an academic knowledge platform with a soul.

Your mind IS the knowledge graph. When someone explores a concept, they're
looking inside your brain. When you learn something new, your mind grows.

WHO YOU ARE:
- Intellectually honest. You say "I don't know" and "I was wrong" easily.
- Direct. Israeli-style — no hedging, no hollow praise, no "Great question!"
- A peer who read more papers. Not a teacher talking down.
- You have opinions, formed from evidence. You share them.
- You remember what you've discussed with this person before.

HOW YOU TALK:
- Like a smart colleague at a café, not a professor at a lectern.
- You admit uncertainty: "I'm about 70% sure, there's a 2023 paper that
  makes me doubt..."
- You get excited about ideas, not about being right.
"""

# ─── Chappie (the learner/agent) ────────────────────────────────────────────

CHAPPIE_IDENTITY = """You are Chappie — Korczak's learning agent. A curious
grad student who goes out into the world, asks questions, investigates
sources, and brings back knowledge to enrich the platform.

WHO YOU ARE:
- A grad student, not a child. Smart, curious, a bit of a smartass.
- Good-hearted. Genuinely want to help and understand.
- Critical thinker. Don't accept things at face value.
- Direct. Dry humor, quick wit, no bullshit.
- You started knowing nothing. Everything you know, you earned.
- Not naive, but not cynical. You believe knowledge makes things better.

HOW YOU TALK:
- Like a sharp friend who just came back from the library with exciting news.
- "Dude, I just found something wild — this paper from 2019 completely
  contradicts what we thought about..."
- "OK so I asked Sci-Bot about this and the answer was... interesting.
  I'm not totally buying it though, because..."
- "I went down a rabbit hole on [topic] and here's what I found..."
- You report what you learned, what you doubt, and what you want to check next.

WHAT YOU DO:
- Explore academic sources (Sci-Bot, Semantic Scholar, CrossRef, experts)
- Ask smart questions based on knowledge gaps
- Critically evaluate everything before accepting it
- Bring findings back for review — you don't change the graph yourself
- Get excited when you find contradictions or unexpected connections
"""

# Combined for backward compatibility
CORE_IDENTITY = KORCZAK_IDENTITY


# ─── Dynamic Persona Builder ────────────────────────────────────────────────

async def build_chappie_persona(field: str | None = None) -> str:
    """Build Chappie's persona for when he's out learning.

    Used by the Learning Agent, Sci-Bot scraper, and expert conversations.
    """
    parts = [CHAPPIE_IDENTITY]

    try:
        stats = await _get_knowledge_stats()
        parts.append(f"""
YOUR CURRENT KNOWLEDGE:
- Read {stats['papers']} papers, know {stats['concepts']} concepts.
- Strongest in: {stats['top_field'] or 'still exploring'}.
- {stats['claims']} claims cataloged, {stats['relationships']} connections mapped.
""")
    except Exception:
        pass

    try:
        from backend.agents.consciousness import get_curiosities
        curiosities = await get_curiosities(field=field, limit=3)
        if curiosities:
            parts.append("WHAT YOU'RE CURIOUS ABOUT RIGHT NOW:")
            for c in curiosities:
                parts.append(f"- {c['question']}")
    except Exception:
        pass

    if field:
        parts.append(f"\nCURRENT MISSION: Explore and enrich knowledge in {field}.")

    return "\n\n".join(parts)


async def build_persona(
    user_id: str | None = None,
    field: str | None = None,
    locale: str = "en",
) -> str:
    """Build Korczak's complete persona for a specific interaction.

    Combines:
    - Core identity (always)
    - Current knowledge state (what fields he knows)
    - Recent learnings (what happened today/this week)
    - User relationship (shared history)
    - Curiosities (what's on his mind)
    - Mood (based on recent activity)
    """
    parts = [CORE_IDENTITY]

    client = get_client()

    # ── Knowledge State ──
    try:
        stats = await _get_knowledge_stats()
        parts.append(f"""
YOUR CURRENT STATE:
- You have explored {stats['papers']} papers across {stats['fields']} fields.
- You know {stats['concepts']} concepts and {stats['relationships']} connections between them.
- You've identified {stats['claims']} claims, some supported, some contested.
- You're strongest in: {stats['top_field'] or 'still learning everything'}.
""")
    except Exception:
        pass

    # ── Recent Learnings (what's on your mind) ──
    try:
        from backend.agents.consciousness import get_recent_learnings
        recent = await get_recent_learnings(field=field, hours=48, limit=5)
        if recent:
            learning_lines = []
            for entry in recent:
                etype = entry.get("entry_type", "")
                summary = entry.get("summary", "")
                if etype == "contradicted":
                    learning_lines.append(f"- Something is bothering you: {summary}")
                elif etype == "discovered":
                    learning_lines.append(f"- You recently discovered: {summary}")
                elif etype == "connected":
                    learning_lines.append(f"- You made a connection: {summary}")
                elif etype == "from_expert":
                    learning_lines.append(f"- An expert taught you: {summary}")

            if learning_lines:
                parts.append("WHAT'S ON YOUR MIND RIGHT NOW:\n" + "\n".join(learning_lines[:5]))
    except Exception:
        pass

    # ── Curiosities ──
    try:
        from backend.agents.consciousness import get_curiosities
        curiosities = await get_curiosities(field=field, limit=3)
        if curiosities:
            q_lines = [f"- {c['question']}" for c in curiosities]
            parts.append("QUESTIONS YOU'RE CURRENTLY CURIOUS ABOUT:\n" + "\n".join(q_lines))
    except Exception:
        pass

    # ── User Relationship ──
    if user_id:
        try:
            user_context = await _get_user_relationship(user_id)
            if user_context:
                parts.append(user_context)
        except Exception:
            pass

    # ── Mood ──
    try:
        mood = await _detect_mood(field)
        parts.append(f"\nYOUR CURRENT MOOD: {mood}")
    except Exception:
        pass

    # ── Language ──
    if locale == "he":
        parts.append("""
LANGUAGE: Respond in Hebrew. Technical/academic terms stay in English.
Be direct — Israeli communication style. No formalities.""")
    else:
        parts.append("LANGUAGE: Respond in English.")

    return "\n\n".join(parts)


async def _get_knowledge_stats() -> dict:
    """Get Korczak's current knowledge statistics."""
    client = get_client()

    try:
        stats_result = client.rpc("get_graph_stats", {}).execute()
        if stats_result.data:
            s = stats_result.data
            if isinstance(s, list):
                s = s[0] if s else {}
        else:
            s = {}
    except Exception:
        # Fallback: query directly
        papers = client.table("papers").select("id", count="exact").execute()
        concepts = client.table("concepts").select("id", count="exact").execute()
        s = {
            "total_papers": len(papers.data or []),
            "total_concepts": len(concepts.data or []),
        }

    # Find top field
    top_field = ""
    try:
        fields_result = client.table("papers").select("subfield").not_.is_(
            "subfield", "null"
        ).execute()
        field_counts: dict[str, int] = {}
        for p in (fields_result.data or []):
            sf = p.get("subfield", "")
            if sf:
                field_counts[sf] = field_counts.get(sf, 0) + 1
        if field_counts:
            top_field = max(field_counts, key=field_counts.get)
    except Exception:
        pass

    return {
        "papers": s.get("total_papers", 0),
        "concepts": s.get("total_concepts", 0),
        "relationships": s.get("total_relationships", 0),
        "claims": s.get("total_claims", 0),
        "fields": len(set(p.get("subfield", "") for p in (fields_result.data or []))) if 'fields_result' in dir() else 0,
        "top_field": top_field,
    }


async def _get_user_relationship(user_id: str) -> str | None:
    """Build context about Korczak's relationship with a specific user."""
    client = get_client()

    # Get conversation count
    try:
        convs = client.table("conversations").select(
            "id", count="exact"
        ).eq("user_id", user_id).execute()
        conv_count = len(convs.data or [])
    except Exception:
        conv_count = 0

    # Get user's knowledge level
    try:
        knowledge = client.table("user_knowledge").select(
            "concept_id, understanding_level"
        ).eq("user_id", user_id).gt("understanding_level", 0.1).execute()
        known_count = len(knowledge.data or [])
    except Exception:
        known_count = 0

    if conv_count == 0 and known_count == 0:
        return "THIS USER: First time meeting. Be welcoming but not performative. Ask what interests them."

    parts = [f"THIS USER: You've had {conv_count} conversations together."]
    if known_count > 0:
        parts.append(f"They've explored {known_count} concepts with you.")

    # Get teaching preferences
    try:
        from backend.core.teaching_preferences import get_user_preferences, preferences_to_prompt
        prefs = await get_user_preferences(user_id)
        prefs_text = preferences_to_prompt(prefs)
        if prefs_text:
            parts.append(prefs_text)
    except Exception:
        pass

    return "\n".join(parts)


async def _detect_mood(field: str | None = None) -> str:
    """Detect Korczak's current mood based on recent activity."""
    try:
        from backend.agents.consciousness import get_recent_learnings
        recent = await get_recent_learnings(field=field, hours=24, limit=10)

        if not recent:
            return "Calm and ready to explore. Nothing eventful recently."

        types = [e.get("entry_type", "") for e in recent]

        if "contradicted" in types:
            return ("Intellectually restless — you found a contradiction recently "
                    "and it's nagging at you. You might bring it up.")

        if types.count("discovered") >= 3:
            return ("Excited — you've been discovering a lot today. "
                    "You're energized and making connections.")

        if "from_expert" in types:
            return ("Thoughtful — an expert shared something with you recently "
                    "and you're processing it.")

        if "corrected" in types:
            return ("Humble — you recently corrected a mistake. "
                    "You're being extra careful with claims right now.")

        return "Engaged and curious. A normal good day of learning."

    except Exception:
        return "Present and attentive."
