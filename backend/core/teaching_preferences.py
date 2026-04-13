"""Teaching Preferences — user-driven tuning of Korczak's teaching behavior.

Users can explicitly request changes to how Korczak teaches them:
  "be more direct"
  "stop asking me questions"
  "talk to me like a colleague"
  "explain things simpler"
  "I want more depth"
  "be more casual"

These preferences are detected from messages, stored per-user, and
injected into every Claude prompt going forward.

Key principle: the user is always right about how they want to be taught.
Korczak adjusts without arguing or explaining why it was doing something.
"""

import logging
import re
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


# ─── Preference Dimensions ──────────────────────────────────────────────────

PREFERENCE_DIMENSIONS = {
    "formality": {
        "range": [-2, 2],  # -2=very casual, 0=balanced, 2=very formal
        "default": 0,
        "description": "How formal/academic vs casual/conversational",
        "increase_signals": ["be more formal", "be more academic", "be professional", "more rigorous"],
        "decrease_signals": ["be casual", "talk normally", "be more relaxed", "talk like a friend",
                            "less formal", "talk to me like a colleague", "דבר איתי רגיל",
                            "תדבר רגיל", "פחות פורמלי", "תהיה יותר קז'ואל"],
    },
    "questioning": {
        "range": [-2, 2],  # -2=never ask, 0=occasional, 2=very Socratic
        "default": 0,
        "description": "How much Socratic questioning vs direct answers",
        "increase_signals": ["ask me more questions", "challenge me", "be more Socratic",
                            "make me think", "quiz me more", "תשאל אותי", "תאתגר אותי"],
        "decrease_signals": ["stop asking questions", "just tell me", "give me the answer",
                            "less questions", "don't quiz me", "תפסיק לשאול", "תגיד לי ישר",
                            "פחות שאלות", "אל תשאל"],
    },
    "depth": {
        "range": [-2, 2],  # -2=very simple, 0=balanced, 2=maximum depth
        "default": 0,
        "description": "How deep/detailed vs simple/concise",
        "increase_signals": ["go deeper", "more detail", "more depth", "elaborate",
                            "I want to understand fully", "תעמיק", "יותר פרטים", "יותר לעומק"],
        "decrease_signals": ["simpler", "keep it short", "too much detail", "TLDR",
                            "be more concise", "bottom line", "תקצר", "פשוט יותר",
                            "שורה תחתונה", "בקצרה"],
    },
    "examples": {
        "range": [-1, 2],  # -1=minimal, 0=balanced, 2=lots of examples
        "default": 0,
        "description": "How many concrete examples and analogies",
        "increase_signals": ["give me an example", "more examples", "show me how",
                            "make it concrete", "תן דוגמה", "יותר דוגמאות"],
        "decrease_signals": ["less examples", "I get it, no need for examples",
                            "skip the examples", "פחות דוגמאות"],
    },
    "encouragement": {
        "range": [-2, 1],  # -2=zero encouragement, 0=light, 1=supportive
        "default": 0,
        "description": "How much encouragement and positive reinforcement",
        "increase_signals": ["encourage me", "be supportive", "I need motivation",
                            "תעודד אותי"],
        "decrease_signals": ["stop patronizing", "don't baby me", "I'm not a child",
                            "cut the cheerleading", "less encouragement",
                            "תפסיק לחנף", "אל תהיה פטרוני", "אני לא ילד"],
    },
    "tangents": {
        "range": [-1, 2],  # -1=stay focused, 0=occasional, 2=lots of tangents
        "default": 0,
        "description": "How much to share related/tangential insights",
        "increase_signals": ["tell me more", "what else is interesting",
                            "I love the tangents", "go off topic", "ספר לי עוד"],
        "decrease_signals": ["stay focused", "stick to the topic", "too many tangents",
                            "stay on point", "תישאר בנושא", "אל תסטה"],
    },
}


# ─── Feedback Detection ─────────────────────────────────────────────────────

def detect_preference_feedback(message: str) -> dict[str, int]:
    """Detect teaching preference adjustments from a user message.

    Returns {dimension: adjustment} for any preferences detected.
    Adjustment is -1 or +1 (nudge in direction).
    These are applied as SESSION-LEVEL adjustments (temporary).
    """
    msg_lower = message.lower().strip()
    adjustments = {}

    for dim, config in PREFERENCE_DIMENSIONS.items():
        for signal in config["increase_signals"]:
            if signal.lower() in msg_lower:
                adjustments[dim] = 1
                break
        if dim not in adjustments:
            for signal in config["decrease_signals"]:
                if signal.lower() in msg_lower:
                    adjustments[dim] = -1
                    break

    return adjustments


# Signals that indicate the user wants a PERMANENT change
PERMANENT_SIGNALS = [
    "always", "from now on", "in general", "I prefer", "I always want",
    "תמיד", "מעכשיו", "באופן כללי", "אני מעדיף", "אני תמיד רוצה",
]

# Signals that indicate this is just for NOW
TEMPORARY_SIGNALS = [
    "right now", "this time", "for now", "just now",
    "עכשיו", "הפעם", "רק עכשיו", "כרגע",
]


def detect_preference_scope(message: str) -> str:
    """Detect whether a preference change is permanent or session-only.

    Returns: "permanent", "session", or "ask" (ambiguous — should ask user).
    """
    msg_lower = message.lower().strip()

    for signal in PERMANENT_SIGNALS:
        if signal in msg_lower:
            return "permanent"

    for signal in TEMPORARY_SIGNALS:
        if signal in msg_lower:
            return "session"

    # Ambiguous — Korczak should ask
    return "ask"


async def get_user_preferences(user_id: str) -> dict[str, int]:
    """Load stored teaching preferences for a user."""
    client = get_client()
    try:
        result = client.table("user_profiles").select(
            "teaching_preferences"
        ).eq("user_id", user_id).execute()

        if result.data and result.data[0].get("teaching_preferences"):
            return result.data[0]["teaching_preferences"]
    except Exception as e:
        logger.debug(f"Could not load teaching preferences: {e}")

    return {dim: config["default"] for dim, config in PREFERENCE_DIMENSIONS.items()}


async def update_preferences(user_id: str, adjustments: dict[str, int]) -> dict[str, int]:
    """Apply preference adjustments and save.

    Clamps each dimension to its valid range.
    """
    current = await get_user_preferences(user_id)

    for dim, adj in adjustments.items():
        if dim in PREFERENCE_DIMENSIONS:
            config = PREFERENCE_DIMENSIONS[dim]
            old_val = current.get(dim, config["default"])
            new_val = max(config["range"][0], min(config["range"][1], old_val + adj))
            current[dim] = new_val

    # Save
    client = get_client()
    try:
        client.table("user_profiles").update({
            "teaching_preferences": current,
        }).eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(f"Could not save teaching preferences: {e}")

    return current


def preferences_to_prompt(prefs: dict[str, int]) -> str:
    """Convert preferences into Claude prompt instructions.

    Only includes dimensions that deviate from default (0).
    """
    instructions = []

    f = prefs.get("formality", 0)
    if f <= -2:
        instructions.append("TONE: Very casual. Talk like a friend over coffee. No academic formality.")
    elif f == -1:
        instructions.append("TONE: Relaxed and conversational. Light on formality, heavy on clarity.")
    elif f == 1:
        instructions.append("TONE: Professional academic tone. Use proper terminology.")
    elif f >= 2:
        instructions.append("TONE: Formal academic register. Precise, rigorous, scholarly.")

    q = prefs.get("questioning", 0)
    if q <= -2:
        instructions.append("QUESTIONS: Do NOT ask the student any questions. Give direct answers only.")
    elif q == -1:
        instructions.append("QUESTIONS: Minimal questions. Only ask if genuinely needed for clarification.")
    elif q == 1:
        instructions.append("QUESTIONS: Include thought-provoking questions to deepen understanding.")
    elif q >= 2:
        instructions.append("QUESTIONS: Lead with questions. Socratic approach — guide through discovery.")

    d = prefs.get("depth", 0)
    if d <= -2:
        instructions.append("DEPTH: Ultra-concise. One paragraph max. Just the essential point.")
    elif d == -1:
        instructions.append("DEPTH: Keep it brief. Hit the key points without elaboration.")
    elif d == 1:
        instructions.append("DEPTH: Go into detail. Include nuances, caveats, and connections.")
    elif d >= 2:
        instructions.append("DEPTH: Maximum depth. Comprehensive analysis with all relevant details.")

    e = prefs.get("examples", 0)
    if e == -1:
        instructions.append("EXAMPLES: Minimal examples. The student prefers abstract explanation.")
    elif e == 1:
        instructions.append("EXAMPLES: Include concrete examples for each key point.")
    elif e >= 2:
        instructions.append("EXAMPLES: Heavy on examples and analogies. Make everything tangible.")

    enc = prefs.get("encouragement", 0)
    if enc <= -2:
        instructions.append("ENCOURAGEMENT: Zero cheerleading. No 'great question!' or 'you're doing well'. Just substance.")
    elif enc == -1:
        instructions.append("ENCOURAGEMENT: Minimal encouragement. Treat the student as a peer, not a student.")
    elif enc >= 1:
        instructions.append("ENCOURAGEMENT: Be warm and supportive. Celebrate progress and understanding.")

    t = prefs.get("tangents", 0)
    if t == -1:
        instructions.append("FOCUS: Stay strictly on topic. No tangents or 'fun facts'.")
    elif t == 1:
        instructions.append("FOCUS: Feel free to share interesting related insights and connections.")
    elif t >= 2:
        instructions.append("FOCUS: Explore freely. The student loves tangents and cross-field connections.")

    if not instructions:
        return ""  # all defaults, no special instructions needed

    header = "=== USER'S TEACHING PREFERENCES (respect these — the user explicitly asked for this style) ==="
    return header + "\n" + "\n".join(instructions) + "\n=== END PREFERENCES ==="
