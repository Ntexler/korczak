"""Level Detector — estimates user expertise from vocabulary and question patterns.

Four levels:
  0 = child (ages 8-12): simple vocabulary, "what is" questions
  1 = highschool (13-18): basic field terminology, "how does" questions
  2 = student (undergrad/grad): uses jargon correctly, asks about methodology
  3 = researcher: specialized vocabulary, asks about controversies/gaps/methods

Key rule: Always respond ONE level below detected (user feels successful).
Detection is implicit — never ask "what's your level?"
"""

import re
from collections import Counter


# Academic jargon tiers
_RESEARCHER_TERMS = {
    "epistemology", "ontology", "phenomenology", "hermeneutic", "heuristic",
    "paradigm shift", "operationalize", "reification", "praxis", "dialectic",
    "positionality", "reflexivity", "autoethnography", "intersubjectivity",
    "ethnomethodology", "thick description", "habitus", "liminality",
    "hegemony", "subaltern", "intersectionality", "biopolitics",
    "necropolitics", "cosmopolitics", "multispecies", "assemblage",
    "rhizome", "deterritorialization", "genealogy", "dispositif",
    "performativity", "affect theory", "new materialism",
    "posthumanism", "decolonial", "indigenous methodology",
    "p-value", "regression", "meta-analysis", "systematic review",
    "longitudinal", "mixed methods", "grounded theory",
    "discourse analysis", "critical race theory",
}

_STUDENT_TERMS = {
    "methodology", "qualitative", "quantitative", "ethnography",
    "participant observation", "fieldwork", "case study", "literature review",
    "theoretical framework", "hypothesis", "variable", "correlation",
    "peer review", "citation", "abstract", "empirical", "normative",
    "socialization", "globalization", "neoliberal", "postcolonial",
    "structuralism", "functionalism", "symbolic", "agency", "structure",
    "cultural relativism", "ethnocentrism", "kinship", "ritual",
    "classification", "taxonomy", "paradigm", "discourse",
}

_HIGHSCHOOL_TERMS = {
    "culture", "society", "tradition", "custom", "belief",
    "evolution", "theory", "research", "study", "experiment",
    "population", "community", "identity", "diversity",
    "civilization", "anthropology", "sociology", "psychology",
}

# Question complexity patterns
_SIMPLE_PATTERNS = [
    r"^what\s+is\b", r"^who\s+(is|was)\b", r"^where\s+is\b",
    r"^when\s+(did|was)\b", r"^is\s+it\s+true\b",
    r"^מה\s+זה\b", r"^מי\s+זה\b",
]

_INTERMEDIATE_PATTERNS = [
    r"\bhow\s+does\b", r"\bwhy\s+is\b", r"\bwhat\s+are\s+the\s+main\b",
    r"\bwhat'?s\s+the\s+difference\b", r"\bcompare\b",
    r"\bexamples?\s+of\b", r"\brelationship\s+between\b",
]

_ADVANCED_PATTERNS = [
    r"\bmethodological\b", r"\bepistemological\b", r"\bontological\b",
    r"\bcritique\b", r"\blimitations?\b", r"\bimplications?\b",
    r"\bgaps?\s+in\b", r"\bunderrepresented\b", r"\boverlooked\b",
    r"\bparadigm\b", r"\breplication\b", r"\bvalidity\b",
    r"\bhow\s+has\s+.+\s+been\s+critiqued\b",
    r"\bwhat\s+are\s+the\s+debates?\b",
    r"\bwhere\s+is\s+.+\s+failing\b",
    r"\bblind\s+spots?\b", r"\bwhite\s+space\b",
]


def detect_level(
    message: str,
    history: list[dict] | None = None,
    current_estimate: int | None = None,
) -> int:
    """Estimate user expertise level from message content.

    Args:
        message: Current user message.
        history: Optional conversation history for cumulative analysis.
        current_estimate: Previous level estimate (for smoothing).

    Returns:
        Level 0-3 (child, highschool, student, researcher).
    """
    # Combine current message with recent history for better signal
    texts = [message]
    if history:
        for msg in history[-6:]:
            if msg.get("role") == "user":
                texts.append(msg.get("content", ""))
    combined = " ".join(texts).lower()

    # Count term hits at each level
    words = set(re.findall(r'[\w\'-]+', combined))
    bigrams = set()
    word_list = combined.split()
    for i in range(len(word_list) - 1):
        bigrams.add(f"{word_list[i]} {word_list[i+1]}")

    all_terms = words | bigrams

    researcher_hits = len(all_terms & _RESEARCHER_TERMS)
    student_hits = len(all_terms & _STUDENT_TERMS)
    highschool_hits = len(all_terms & _HIGHSCHOOL_TERMS)

    # Check question complexity
    simple_q = any(re.search(p, message, re.IGNORECASE) for p in _SIMPLE_PATTERNS)
    intermediate_q = any(re.search(p, message, re.IGNORECASE) for p in _INTERMEDIATE_PATTERNS)
    advanced_q = any(re.search(p, message, re.IGNORECASE) for p in _ADVANCED_PATTERNS)

    # Score
    score = 0

    # Term-based scoring
    if researcher_hits >= 2:
        score += 3
    elif researcher_hits == 1:
        score += 2
    if student_hits >= 3:
        score += 2
    elif student_hits >= 1:
        score += 1
    if highschool_hits >= 2:
        score += 1

    # Question complexity scoring
    if advanced_q:
        score += 2
    elif intermediate_q:
        score += 1
    elif simple_q:
        score -= 1

    # Message length heuristic (longer = more sophisticated)
    if len(message) > 200:
        score += 1
    elif len(message) < 30:
        score -= 1

    # Map score to level
    if score >= 5:
        level = 3  # researcher
    elif score >= 3:
        level = 2  # student
    elif score >= 1:
        level = 1  # highschool
    else:
        level = 0  # child

    # Smooth with previous estimate (don't jump more than 1 level)
    if current_estimate is not None:
        if level > current_estimate + 1:
            level = current_estimate + 1
        elif level < current_estimate - 1:
            level = current_estimate - 1

    return level


def response_level(detected: int) -> int:
    """Get the level to respond at (one below detected, min 0).

    This makes the user feel successful — the response is slightly
    below their level so they understand it easily.
    """
    return max(0, detected - 1)


LEVEL_NAMES = {
    0: "child",
    1: "highschool",
    2: "student",
    3: "researcher",
}

LEVEL_DESCRIPTIONS = {
    0: "Simple, clear language. Use analogies and everyday examples. Short sentences.",
    1: "Clear explanations with basic field terminology. Define jargon when used.",
    2: "Academic language acceptable. Can reference methodologies and theories by name.",
    3: "Full academic discourse. Assume familiarity with the field's debates and methods.",
}
