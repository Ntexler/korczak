"""Behavior Tracker — User Graph Layer 3: learning patterns and behavioral signals.

Tracks:
  - Session patterns: frequency, duration, time-of-day preferences
  - Learning velocity: how fast concepts move from AWARE → UNDERSTANDS → APPLIES
  - Concept difficulty: which concepts take longer for this user
  - Engagement patterns: question depth, follow-up rates, topic switching
  - Optimal teaching strategy: which Socratic level works best per user
"""

import logging
from datetime import datetime, timezone, timedelta
from collections import Counter

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def track_session(user_id: str, message: str, mode: str, concepts: list[dict]):
    """Record a session interaction for behavioral analysis.

    Called after each chat message. Builds up behavioral data over time.
    """
    if not user_id:
        return

    client = get_client()

    # Get or create behavior record
    try:
        existing = (
            client.table("user_profiles")
            .select("id, behavior_data")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        # behavior_data column may not exist yet (migration 005 not run)
        logger.debug("behavior_data column not available — skipping tracking")
        return

    if not existing.data:
        return

    profile = existing.data[0]
    behavior = profile.get("behavior_data") or {}

    now = datetime.now(timezone.utc)
    hour = now.hour

    # --- Update session patterns ---
    sessions = behavior.get("sessions", [])
    # Add compact session record (keep last 100)
    sessions.append({
        "ts": now.isoformat(),
        "hour": hour,
        "mode": mode,
        "msg_len": len(message),
        "concepts": len(concepts),
    })
    if len(sessions) > 100:
        sessions = sessions[-100:]
    behavior["sessions"] = sessions

    # --- Time-of-day preference ---
    hour_counts = behavior.get("hour_counts", {})
    hour_key = str(hour)
    hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1
    behavior["hour_counts"] = hour_counts

    # --- Mode preference ---
    mode_counts = behavior.get("mode_counts", {})
    mode_counts[mode] = mode_counts.get(mode, 0) + 1
    behavior["mode_counts"] = mode_counts

    # --- Message complexity trend ---
    avg_msg_len = behavior.get("avg_msg_len", 0)
    msg_count = behavior.get("total_messages", 0)
    new_count = msg_count + 1
    behavior["avg_msg_len"] = round((avg_msg_len * msg_count + len(message)) / new_count, 1)
    behavior["total_messages"] = new_count

    # --- Concept engagement breadth ---
    concept_ids_seen = set(behavior.get("concepts_seen", []))
    for c in concepts:
        cid = c.get("id")
        if cid:
            concept_ids_seen.add(cid)
    behavior["concepts_seen"] = list(concept_ids_seen)[-200:]  # Cap at 200
    behavior["unique_concepts"] = len(concept_ids_seen)

    # --- Save ---
    try:
        client.table("user_profiles").update({
            "behavior_data": behavior,
            "updated_at": now.isoformat(),
        }).eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(f"Behavior tracking failed for {user_id}: {e}")


async def get_learning_velocity(user_id: str) -> dict:
    """Calculate how fast concepts progress through understanding levels.

    Returns average time from first encounter to each level transition.
    """
    client = get_client()

    knowledge = (
        client.table("user_knowledge")
        .select("concept_id, understanding_level, interaction_count, last_interaction")
        .eq("user_id", user_id)
        .execute()
    )

    if not knowledge.data:
        return {"status": "insufficient_data", "concepts_tracked": 0}

    levels = Counter()
    total_interactions = 0
    for k in knowledge.data:
        lvl = k.get("understanding_level", 0)
        levels[lvl] += 1
        total_interactions += k.get("interaction_count", 1)

    concepts_count = len(knowledge.data)
    avg_interactions = round(total_interactions / max(concepts_count, 1), 1)

    return {
        "concepts_tracked": concepts_count,
        "level_distribution": dict(levels),
        "avg_interactions_per_concept": avg_interactions,
        "total_interactions": total_interactions,
    }


async def get_engagement_profile(user_id: str) -> dict:
    """Build a comprehensive engagement profile for the user.

    Combines session patterns, learning velocity, and preferences.
    """
    client = get_client()

    # Get behavior data
    try:
        profile_result = (
            client.table("user_profiles")
            .select("behavior_data, role, institution, research_topic, language")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        # behavior_data column may not exist yet
        profile_result = (
            client.table("user_profiles")
            .select("role, institution, research_topic, language")
            .eq("user_id", user_id)
            .execute()
        )

    if not profile_result.data:
        return {"status": "no_profile"}

    profile = profile_result.data[0]
    behavior = profile.get("behavior_data") or {}

    # Calculate derived metrics
    sessions = behavior.get("sessions", [])
    hour_counts = behavior.get("hour_counts", {})
    mode_counts = behavior.get("mode_counts", {})

    # Peak activity hours
    peak_hours = sorted(hour_counts.items(), key=lambda x: -x[1])[:3]
    peak_hours_list = [{"hour": int(h), "count": c} for h, c in peak_hours]

    # Preferred mode
    preferred_mode = max(mode_counts, key=mode_counts.get) if mode_counts else "navigator"

    # Session frequency (sessions per day over last 30 days)
    if sessions:
        now = datetime.now(timezone.utc)
        recent = [s for s in sessions if _parse_ts(s.get("ts", "")) and
                  (now - _parse_ts(s["ts"])).days <= 30]
        sessions_per_day = round(len(recent) / 30, 2) if recent else 0
    else:
        sessions_per_day = 0

    # Average message complexity
    avg_msg_len = behavior.get("avg_msg_len", 0)
    if avg_msg_len > 200:
        complexity = "detailed"
    elif avg_msg_len > 80:
        complexity = "moderate"
    else:
        complexity = "concise"

    # Learning velocity
    velocity = await get_learning_velocity(user_id)

    return {
        "user_id": user_id,
        "role": profile.get("role"),
        "institution": profile.get("institution"),
        "research_topic": profile.get("research_topic"),
        "total_messages": behavior.get("total_messages", 0),
        "unique_concepts_explored": behavior.get("unique_concepts", 0),
        "peak_activity_hours": peak_hours_list,
        "preferred_mode": preferred_mode,
        "sessions_per_day": sessions_per_day,
        "message_complexity": complexity,
        "avg_message_length": avg_msg_len,
        "mode_distribution": mode_counts,
        "learning_velocity": velocity,
    }


async def get_behavior_context_string(user_id: str) -> str:
    """Build a behavior context string for system prompts.

    Adds Layer 3 behavioral insights to the user context.
    """
    if not user_id:
        return ""

    try:
        profile = await get_engagement_profile(user_id)
    except Exception:
        return ""

    if profile.get("status") == "no_profile":
        return ""

    parts = []

    total = profile.get("total_messages", 0)
    if total > 0:
        parts.append(f"Session history: {total} messages, "
                     f"{profile.get('unique_concepts_explored', 0)} concepts explored")

    complexity = profile.get("message_complexity")
    if complexity:
        parts.append(f"Communication style: {complexity}")

    preferred = profile.get("preferred_mode")
    if preferred and preferred != "navigator":
        parts.append(f"Preferred mode: {preferred}")

    velocity = profile.get("learning_velocity", {})
    if velocity.get("concepts_tracked", 0) > 3:
        avg = velocity.get("avg_interactions_per_concept", 0)
        if avg > 5:
            parts.append("Learning pace: takes time to absorb — be patient and thorough")
        elif avg < 2:
            parts.append("Learning pace: quick learner — can handle density")

    if not parts:
        return ""

    return "Behavioral patterns:\n" + "\n".join(f"  - {p}" for p in parts)


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO timestamp string, return None on failure."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
