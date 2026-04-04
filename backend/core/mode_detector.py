"""Mode Detector — auto-detects user intent from message text.

Three modes:
  - navigator: "Tell me about X", "What is X?", "How does X relate to Y?"
  - tutor: "Teach me X", "Explain X step by step", "Help me understand X"
  - briefing: "What's new in X?", "Update me on X", "What changed in X?"

The detector uses keyword patterns + intent signals. Falls back to the
conversation's current mode if ambiguous.
"""

import re

# Pattern groups for each mode
_TUTOR_PATTERNS = [
    r"\bteach\b", r"\bexplain\b.*\bstep\b", r"\bhelp\s+me\s+understand\b",
    r"\bwalk\s+me\s+through\b", r"\bbreak\s+(it\s+)?down\b",
    r"\bwhat\s+do\s+i\s+need\s+to\s+know\b", r"\bprerequisites?\b",
    r"\blearn\b", r"\bstudy\b", r"\bquiz\b", r"\btest\s+me\b",
    r"\bi\s+don'?t\s+understand\b", r"\bconfused\b", r"\bconfusing\b",
    r"\bcan\s+you\s+simplify\b", r"\beli5\b", r"\bfor\s+dummies\b",
    # Hebrew
    r"\bלמד\b", r"\bתסביר\b", r"\bהסבר\b", r"\bעזור\s+לי\s+להבין\b",
    r"\bלא\s+מבין\b", r"\bמבולבל\b", r"\bשלב\s+אחרי\s+שלב\b",
    r"\bבפשטות\b",
]

_BRIEFING_PATTERNS = [
    r"\bwhat'?s\s+new\b", r"\bupdate\s+me\b", r"\bwhat\s+changed\b",
    r"\brecent\s+(developments?|trends?|papers?)\b",
    r"\blatest\b", r"\bthis\s+(week|month|year)\b",
    r"\bbreaking\b", r"\bemerging\b",
    r"\bcatch\s+me\s+up\b", r"\bsummarize\s+recent\b",
    # Hebrew
    r"\bמה\s+חדש\b", r"\bעדכן\s+אותי\b", r"\bמה\s+השתנה\b",
    r"\bהתפתחויות\s+אחרונות\b", r"\bטרנדים?\b",
]

# Compile patterns
_tutor_re = [re.compile(p, re.IGNORECASE) for p in _TUTOR_PATTERNS]
_briefing_re = [re.compile(p, re.IGNORECASE) for p in _BRIEFING_PATTERNS]


def detect_mode(
    message: str,
    current_mode: str = "navigator",
    conversation_history: list[dict] | None = None,
) -> str:
    """Detect the user's intended mode from their message.

    Args:
        message: The user's current message.
        current_mode: The conversation's current mode (used as fallback).
        conversation_history: Optional recent messages for context.

    Returns:
        One of: "navigator", "tutor", "briefing"
    """
    text = message.strip()

    # Score each mode
    tutor_score = sum(1 for p in _tutor_re if p.search(text))
    briefing_score = sum(1 for p in _briefing_re if p.search(text))

    # Explicit mode switches (highest priority)
    explicit_navigator = re.search(
        r"\b(navigate|navigator|נווט)\s+mode\b|\bswitch\s+to\s+navigat", text, re.IGNORECASE
    )
    explicit_tutor = re.search(
        r"\b(tutor|teach|מדריך|למד)\s+mode\b|\bswitch\s+to\s+(tutor|teach)", text, re.IGNORECASE
    )
    explicit_briefing = re.search(
        r"\b(briefing|brief|תדרוך|עדכן)\s+mode\b|\bswitch\s+to\s+brief", text, re.IGNORECASE
    )

    if explicit_tutor:
        return "tutor"
    if explicit_briefing:
        return "briefing"
    if explicit_navigator:
        return "navigator"

    # Pattern-based detection
    if tutor_score >= 2:
        return "tutor"
    if briefing_score >= 2:
        return "briefing"
    if tutor_score == 1 and briefing_score == 0:
        return "tutor"
    if briefing_score == 1 and tutor_score == 0:
        return "briefing"

    # Confusion/frustration signals → switch to tutor
    confusion_signals = [
        r"\bi\s+still\s+don'?t\b", r"\bwhat\s+do\s+you\s+mean\b",
        r"\bthat\s+doesn'?t\s+make\s+sense\b", r"\bhuh\??\b",
        r"\b\?\?\?+\b",
    ]
    if any(re.search(p, text, re.IGNORECASE) for p in confusion_signals):
        return "tutor"

    # Default: keep current mode
    return current_mode
