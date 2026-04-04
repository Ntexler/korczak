"""Context Extractor — extracts personal context from conversations implicitly.

Layer 2 (Personal Context):
  - role: student, researcher, professor, journalist, curious layperson
  - institution: university/org mentioned
  - research_topic: what they're working on
  - interests: recurring themes across conversations
  - deadlines: mentioned deadlines or time pressure
  - language_preference: detected from messages

Updates are implicit — parsed from natural conversation, never asked.
"""

import re
import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Role detection patterns
_ROLE_PATTERNS = {
    "researcher": [
        r"\bmy\s+research\b", r"\bmy\s+paper\b", r"\bmy\s+thesis\b",
        r"\bi'?m\s+researching\b", r"\bmy\s+dissertation\b",
        r"\bmy\s+lab\b", r"\bour\s+findings\b",
        r"\bהמחקר\s+שלי\b", r"\bעבודת\s+הדוקטורט\b",
    ],
    "student": [
        r"\bmy\s+class\b", r"\bmy\s+course\b", r"\bmy\s+professor\b",
        r"\bhomework\b", r"\bassignment\b", r"\bexam\b",
        r"\bi'?m\s+studying\b", r"\bundergrad\b", r"\bgrad\s+student\b",
        r"\bהקורס\s+שלי\b", r"\bסטודנט\b",
    ],
    "professor": [
        r"\bmy\s+students\b", r"\bi\s+teach\b", r"\bmy\s+course\b.*\bteach\b",
        r"\bmy\s+department\b", r"\btenure\b", r"\bsyllabus\b.*\bmy\b",
        r"\bהסטודנטים\s+שלי\b", r"\bאני\s+מלמד\b",
    ],
    "journalist": [
        r"\barticle\b.*\bwriting\b", r"\bmy\s+(article|piece|story)\b",
        r"\breporting\s+on\b", r"\bmy\s+editor\b",
    ],
}

# Institution patterns
_INSTITUTION_RE = re.compile(
    r"(?:at|from|of)\s+((?:university|univ\.?|college|institute|school)\s+of\s+[\w\s]+|"
    r"(?:[\w]+\s+){0,2}(?:university|college|institute|school|lab|center|centre))",
    re.IGNORECASE,
)

# Research topic patterns
_TOPIC_PATTERNS = [
    r"(?:my|our)\s+(?:research|work|thesis|dissertation|paper)\s+(?:is\s+)?(?:on|about|focuses?\s+on|deals?\s+with)\s+(.+?)(?:\.|,|$)",
    r"i'?m\s+(?:studying|researching|working\s+on|interested\s+in|writing\s+about)\s+(.+?)(?:\.|,|$)",
    r"(?:המחקר|העבודה|התזה)\s+שלי\s+(?:על|בנושא|עוסק|עוסקת)\s+(.+?)(?:\.|,|$)",
]

# Deadline patterns
_DEADLINE_PATTERNS = [
    r"(?:deadline|due|submit|defense|presentation)\s+(?:is\s+)?(?:on\s+|by\s+|in\s+)(.+?)(?:\.|,|$)",
    r"(?:need|have)\s+to\s+(?:finish|submit|present)\s+by\s+(.+?)(?:\.|,|$)",
    r"(?:next\s+(?:week|month)|this\s+(?:week|month|semester))\b",
]


def extract_context(message: str) -> dict:
    """Extract personal context signals from a single message.

    Returns dict with detected signals (only non-None values).
    """
    signals = {}
    text = message.strip()

    # Detect role
    for role, patterns in _ROLE_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            signals["role"] = role
            break

    # Detect institution
    inst_match = _INSTITUTION_RE.search(text)
    if inst_match:
        signals["institution"] = inst_match.group(1).strip()

    # Detect research topic
    for pattern in _TOPIC_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            signals["research_topic"] = match.group(1).strip()[:200]
            break

    # Detect deadline pressure
    for pattern in _DEADLINE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            signals["has_deadline"] = True
            break

    # Detect language preference
    hebrew_chars = len(re.findall(r'[\u0590-\u05FF]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    if hebrew_chars > latin_chars and hebrew_chars > 10:
        signals["language_preference"] = "he"
    elif latin_chars > 10:
        signals["language_preference"] = "en"

    return signals


async def update_user_profile(user_id: str, signals: dict):
    """Merge extracted signals into the user's profile."""
    if not user_id or not signals:
        return

    client = get_client()

    # Get existing profile
    existing = (
        client.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    profile = existing.data[0] if existing.data else None

    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    # Merge signals — only update if we have new, non-conflicting data
    if "role" in signals:
        update_data["role"] = signals["role"]
    if "institution" in signals:
        update_data["institution"] = signals["institution"]
    if "research_topic" in signals:
        update_data["research_topic"] = signals["research_topic"]
    if "language_preference" in signals:
        update_data["language"] = signals["language_preference"]

    if profile:
        client.table("user_profiles").update(update_data).eq("user_id", user_id).execute()
    else:
        update_data["user_id"] = user_id
        update_data["display_name"] = "Anonymous"
        try:
            client.table("user_profiles").insert(update_data).execute()
        except Exception as e:
            logger.warning(f"Failed to create profile for {user_id}: {e}")


async def get_rich_user_context(user_id: str) -> str:
    """Build a rich context string from the user's profile + knowledge state.

    Combines Layer 1 (knowledge) + Layer 2 (personal context) for system prompts.
    """
    if not user_id:
        return "Anonymous user — no profile available."

    client = get_client()

    # Get profile
    profile_result = (
        client.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    profile = profile_result.data[0] if profile_result.data else None

    # Get knowledge state
    knowledge = (
        client.table("user_knowledge")
        .select("concept_id, understanding_level, misconceptions")
        .eq("user_id", user_id)
        .execute()
    )

    parts = []

    if profile:
        if profile.get("role"):
            parts.append(f"Role: {profile['role']}")
        if profile.get("institution"):
            parts.append(f"Institution: {profile['institution']}")
        if profile.get("research_topic"):
            parts.append(f"Research topic: {profile['research_topic']}")
        if profile.get("language"):
            parts.append(f"Preferred language: {profile['language']}")

    if knowledge.data:
        levels = {}
        for k in knowledge.data:
            lvl = k.get("understanding_level", 0)
            levels[lvl] = levels.get(lvl, 0) + 1

        level_labels = {0: "unaware", 1: "aware", 2: "understands", 3: "applies", 4: "deep expertise"}
        knowledge_summary = ", ".join(
            f"{count} concepts at '{level_labels.get(lvl, lvl)}' level"
            for lvl, count in sorted(levels.items(), reverse=True)
        )
        parts.append(f"Knowledge state: {knowledge_summary}")

        # Misconceptions
        misconceptions = []
        for k in knowledge.data:
            m = k.get("misconceptions")
            if m:
                if isinstance(m, list):
                    misconceptions.extend(m)
                else:
                    misconceptions.append(str(m))
        if misconceptions:
            parts.append(f"Known misconceptions: {', '.join(misconceptions[:5])}")

    if not parts:
        return "New user — limited profile data available."

    return "User profile:\n" + "\n".join(f"  - {p}" for p in parts)
