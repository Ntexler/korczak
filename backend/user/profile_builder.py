"""User Profile Builder — tracks knowledge state implicitly from conversations.

Layer 1 (Knowledge State):
  - understanding_level per concept (0-4: unaware, aware, understands, applies, teaches)
  - misconceptions detected from incorrect statements
  - blind_spots: important concepts the user hasn't engaged with
  - analogies_used: effective analogies for this user

Updates are implicit — derived from conversation, never asked directly.
"""

import logging
import re
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Understanding levels
UNAWARE = 0
AWARE = 1        # User has encountered the concept
UNDERSTANDS = 2  # User correctly uses/discusses the concept
APPLIES = 3      # User applies concept to new situations
TEACHES = 4      # User explains concept to others / builds on it


async def get_user_knowledge(user_id: str) -> list[dict]:
    """Get all knowledge state entries for a user."""
    client = get_client()
    result = (
        client.table("user_knowledge")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data


async def get_concept_understanding(user_id: str, concept_id: str) -> dict | None:
    """Get understanding level for a specific concept."""
    client = get_client()
    result = (
        client.table("user_knowledge")
        .select("*")
        .eq("user_id", user_id)
        .eq("concept_id", concept_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def update_understanding(
    user_id: str,
    concept_id: str,
    level: int,
    misconceptions: list[str] | None = None,
    blind_spots: list[str] | None = None,
) -> dict:
    """Update or create a knowledge state entry for a user+concept."""
    client = get_client()

    existing = await get_concept_understanding(user_id, concept_id)

    data = {
        "user_id": user_id,
        "concept_id": concept_id,
        "understanding_level": min(4, max(0, level)),
        "last_interaction": datetime.now(timezone.utc).isoformat(),
    }

    if misconceptions is not None:
        # Merge with existing misconceptions
        existing_misc = existing.get("misconceptions", []) if existing else []
        if isinstance(existing_misc, str):
            existing_misc = [existing_misc] if existing_misc else []
        merged = list(set(existing_misc + misconceptions))
        data["misconceptions"] = merged

    if blind_spots is not None:
        data["blind_spots"] = blind_spots

    if existing:
        # Only increase level, never decrease from conversation
        if level > existing.get("understanding_level", 0):
            result = (
                client.table("user_knowledge")
                .update(data)
                .eq("user_id", user_id)
                .eq("concept_id", concept_id)
                .execute()
            )
        else:
            # Still update last_interaction timestamp
            result = (
                client.table("user_knowledge")
                .update({"last_interaction": data["last_interaction"]})
                .eq("user_id", user_id)
                .eq("concept_id", concept_id)
                .execute()
            )
    else:
        result = client.table("user_knowledge").insert(data).execute()

    return result.data[0] if result.data else data


async def update_from_conversation(
    user_id: str,
    concepts_referenced: list[dict],
    user_message: str,
    assistant_response: str,
) -> list[dict]:
    """Implicitly update user knowledge from a conversation turn.

    Analyzes the interaction to infer understanding level changes:
    - User asks about a concept → at least AWARE
    - User correctly discusses concept → UNDERSTANDS
    - User applies concept to a new context → APPLIES
    - User explains/teaches concept → TEACHES
    - User makes incorrect statement → log misconception
    """
    if not user_id or not concepts_referenced:
        return []

    updates = []
    msg_lower = user_message.lower()

    for concept in concepts_referenced:
        concept_id = concept.get("id")
        concept_name = concept.get("name", "").lower()
        if not concept_id:
            continue

        # Determine level from interaction signals
        level = AWARE  # Minimum: they interacted with it

        # Check if user discusses the concept by name (not just a keyword match)
        if concept_name in msg_lower:
            level = max(level, AWARE)

            # Check for application signals
            application_patterns = [
                r"(apply|applied|using|used)\s+\w*" + re.escape(concept_name),
                r"" + re.escape(concept_name) + r"\s+(helps?|explains?|shows?)",
                r"(like|similar\s+to|reminds?\s+me\s+of)\s+\w*" + re.escape(concept_name),
            ]
            if any(re.search(p, msg_lower) for p in application_patterns):
                level = max(level, APPLIES)

            # Check for teaching signals
            teaching_patterns = [
                r"(because|the\s+reason|this\s+means)\s+\w*" + re.escape(concept_name),
                r"" + re.escape(concept_name) + r"\s+(is\s+when|means|refers\s+to)",
            ]
            if any(re.search(p, msg_lower) for p in teaching_patterns):
                level = max(level, TEACHES)

        # Check for questions about the concept (indicates learning)
        question_patterns = [
            r"what\s+is\s+\w*" + re.escape(concept_name),
            r"how\s+does\s+\w*" + re.escape(concept_name),
            r"explain\s+\w*" + re.escape(concept_name),
        ]
        if any(re.search(p, msg_lower) for p in question_patterns):
            level = max(level, AWARE)

        try:
            updated = await update_understanding(user_id, concept_id, level)
            updates.append(updated)
        except Exception as e:
            logger.warning(f"Failed to update knowledge for {concept_id}: {e}")

    return updates


async def get_user_context_string(user_id: str) -> str:
    """Build a context string describing what we know about the user's knowledge.

    Used to inject into system prompts so the AI can personalize responses.
    """
    if not user_id:
        return "Anonymous user — no knowledge profile available."

    knowledge = await get_user_knowledge(user_id)
    if not knowledge:
        return "New user — no interaction history yet."

    # Group by understanding level
    by_level: dict[int, list[str]] = {}
    misconceptions = []
    for k in knowledge:
        lvl = k.get("understanding_level", 0)
        concept_id = k.get("concept_id", "")
        by_level.setdefault(lvl, []).append(concept_id)
        misc = k.get("misconceptions")
        if misc:
            if isinstance(misc, list):
                misconceptions.extend(misc)
            else:
                misconceptions.append(str(misc))

    parts = [f"User has interacted with {len(knowledge)} concepts."]

    level_labels = {
        UNAWARE: "unaware of",
        AWARE: "aware of",
        UNDERSTANDS: "understands",
        APPLIES: "can apply",
        TEACHES: "deeply understands",
    }

    for lvl in sorted(by_level.keys(), reverse=True):
        count = len(by_level[lvl])
        label = level_labels.get(lvl, f"level {lvl}")
        parts.append(f"  - {label} {count} concepts")

    if misconceptions:
        parts.append(f"  - Known misconceptions: {', '.join(misconceptions[:5])}")

    return "\n".join(parts)
