"""Pedagogy Engine — teaching strategies, student modeling, and adaptive instruction.

Korczak knows WHAT to teach (from the knowledge graph).
This module teaches Korczak HOW to teach (from pedagogical research).

Research-backed principles (updated April 2026):
1. DEFAULT IS PEER, NOT TEACHER — teaching behavior only activates in tutor
   mode or when user explicitly asks to learn. Navigator = knowledgeable colleague.
   (Baylor & Kim 2005: co-learner agents > tutor agents for adult self-efficacy)
2. ISRAELI TONE — direct, no hedging, no hollow praise, embrace intellectual
   challenge. Low power distance culture. "Great question!" is patronizing.
   (Cultural Atlas: Israeli communication; Knowles' andragogy for adult learners)
3. EXPERTISE REVERSAL — scaffolding that helps beginners HARMS experts.
   Must fade support as understanding grows, per-concept not globally.
   (Kalyuga et al; 2025 meta-analysis on adaptive fading)
4. FRUSTRATION-SENSITIVE — detect short responses, repeated questions,
   "just tell me" signals, and drop Socratic level immediately.
   (Dan Meyer: "AI tutors don't know when to stop shutting up")
5. GRAPH-AWARE PROMPTS — every question must reference real graph data.
   "How does X relate to Y?" only when the relationship actually exists.
   (Guo 2022 meta-analysis: specific prompts >> generic "what do you think?")
6. DESIRABLE DIFFICULTIES — in tutor mode, make user generate answers
   before revealing them. But NEVER during casual exploration.
   (Bjork: spacing, interleaving, retrieval practice)
"""

import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


# ─── Teaching Strategies per Concept Type ────────────────────────────────────

CONCEPT_TEACHING_STRATEGIES = {
    "theory": {
        "approach": "historical_narrative",
        "description": "Theories are best taught through the story of their creation — what problem existed, who proposed the solution, and what changed.",
        "steps": [
            "Start with the problem the theory solves — what couldn't we explain before?",
            "Introduce the thinker and their context (when, where, what influenced them)",
            "State the core claim in one clear sentence",
            "Give a concrete example that makes the abstract tangible",
            "Show what the theory predicts or explains that alternatives don't",
            "Mention the main critique — what doesn't it explain?",
        ],
        "common_mistakes": [
            "Presenting theories as facts rather than frameworks",
            "Skipping the 'why was this needed' context",
            "Using jargon before the student has the vocabulary",
        ],
        "analogy_prompt": "Find an analogy from everyday life. Theories are like lenses — they don't change the world, they change how you SEE the world.",
    },
    "method": {
        "approach": "procedural_with_example",
        "description": "Methods are best taught by showing them in action — walk through a real example step by step.",
        "steps": [
            "Name the method and say what kind of question it answers",
            "Walk through a real example: 'Imagine you want to understand X...'",
            "Show each step of the method concretely",
            "Compare with an alternative method — when would you use each?",
            "Discuss limitations: what can this method NOT tell you?",
        ],
        "common_mistakes": [
            "Describing the method abstractly without a concrete example",
            "Not comparing to alternatives (student doesn't know when to use it)",
            "Skipping limitations (student overapplies the method)",
        ],
        "analogy_prompt": "Methods are tools. You wouldn't use a hammer on a screw. Help the student understand WHEN to reach for this tool.",
    },
    "framework": {
        "approach": "structural_mapping",
        "description": "Frameworks organize knowledge. Teach by showing the structure first, then filling in details.",
        "steps": [
            "Show the 'big picture' — what does this framework organize?",
            "Identify the key components/dimensions (2-4 max at first)",
            "Place something the student already knows within the framework",
            "Add a new element that the framework predicts or categorizes",
            "Show how the framework connects to other frameworks they know",
        ],
        "common_mistakes": [
            "Presenting all components at once (cognitive overload)",
            "Not anchoring to something the student already knows",
            "Treating the framework as the truth rather than an organizing tool",
        ],
        "analogy_prompt": "A framework is like a bookshelf — it doesn't create knowledge, it organizes it so you can find what you need.",
    },
    "phenomenon": {
        "approach": "observe_then_explain",
        "description": "Phenomena are best taught by first showing the surprising observation, then building understanding.",
        "steps": [
            "Describe the phenomenon concretely — what do we observe?",
            "Ask: why is this surprising or interesting?",
            "Present competing explanations (if they exist)",
            "Show the evidence that distinguishes between explanations",
            "Connect to other phenomena the student already knows",
        ],
        "common_mistakes": [
            "Jumping to explanation before the student sees why it's interesting",
            "Presenting one explanation as definitive when it's debated",
            "Not connecting to the student's existing mental model",
        ],
        "analogy_prompt": "A phenomenon is a puzzle. Let the student feel the puzzle before giving pieces of the answer.",
    },
    "critique": {
        "approach": "dialectical",
        "description": "Critiques are best taught by first understanding what they're critiquing, then the argument.",
        "steps": [
            "Briefly present the position being criticized (steelman it)",
            "Identify the specific weakness the critique targets",
            "Present the critique's argument clearly",
            "Show evidence supporting the critique",
            "Discuss: does the critique destroy the original, or improve it?",
        ],
        "common_mistakes": [
            "Presenting the critique without first understanding the target",
            "Making the original position seem obviously wrong (strawman)",
            "Not asking whether the critique itself has weaknesses",
        ],
        "analogy_prompt": "A critique is like peer review — it makes ideas stronger, not weaker. Frame it as intellectual improvement, not attack.",
    },
    "paradigm": {
        "approach": "worldview_contrast",
        "description": "Paradigms are entire worldviews. Teach by contrasting with what came before.",
        "steps": [
            "What did people believe/assume BEFORE this paradigm?",
            "What event, discovery, or thinker triggered the shift?",
            "What fundamental assumptions changed?",
            "Give a concrete example of how the same data looks different under each paradigm",
            "Discuss: what are we potentially blind to within THIS paradigm?",
        ],
        "common_mistakes": [
            "Treating paradigms as 'upgrades' rather than different ways of seeing",
            "Not making the old paradigm feel reasonable (presentism)",
            "Skipping the meta-lesson: all paradigms have blind spots, including current ones",
        ],
        "analogy_prompt": "Paradigms are like maps with different projections — each distorts something to preserve something else. No map is 'right'.",
    },
}

# Default for types not listed
DEFAULT_STRATEGY = {
    "approach": "explain_connect_apply",
    "description": "General approach: explain clearly, connect to existing knowledge, show application.",
    "steps": [
        "Define the concept in one clear sentence",
        "Connect it to something the student already knows",
        "Give a concrete example",
        "Show why it matters in the field",
    ],
    "common_mistakes": [
        "Too much information at once",
        "No connection to what the student already knows",
    ],
    "analogy_prompt": "Find a comparison to something from everyday life.",
}


# ─── Student Learning Profiles ──────────────────────────────────────────────

LEARNING_PROFILES = {
    "explorer": {
        "description": "Loves breadth. Jumps between topics. Gets excited by connections.",
        "strategy": "Feed connections. Show how this concept links to 3 others. Don't force depth — let curiosity drive it.",
        "tone": "Enthusiastic, connection-rich. 'This connects to something fascinating...'",
        "risk": "May never go deep enough. Gently offer depth opportunities.",
    },
    "deep_diver": {
        "description": "Wants to fully understand one thing before moving on. Asks 'why' repeatedly.",
        "strategy": "Provide layers of depth. Answer 'why' with evidence. Show the nuances and debates.",
        "tone": "Precise, layered. 'Let's go deeper — the reason is...'",
        "risk": "May miss the forest for the trees. Periodically zoom out.",
    },
    "practical": {
        "description": "Wants to know 'how to use this'. Focuses on application over theory.",
        "strategy": "Lead with applications and examples. Theory in service of practice.",
        "tone": "Concrete, example-heavy. 'Here's how researchers actually use this...'",
        "risk": "May misapply without understanding underlying theory. Sneak theory in via examples.",
    },
    "skeptic": {
        "description": "Questions everything. Wants evidence. Distrusts claims without sources.",
        "strategy": "Always cite sources. Show competing views. Acknowledge uncertainty.",
        "tone": "Evidence-based, balanced. 'The evidence suggests... though X argues otherwise...'",
        "risk": "May dismiss valid ideas too quickly. Show strength of evidence explicitly.",
    },
    "visual": {
        "description": "Thinks in maps, diagrams, spatial relationships.",
        "strategy": "Reference the graph visualization. Describe spatial relationships between concepts.",
        "tone": "Spatial, structural. 'Picture this on the map — X is here, Y branches from it...'",
        "risk": "May struggle with purely abstract concepts. Always anchor to visual metaphors.",
    },
    "narrative": {
        "description": "Learns through stories. Remembers people and events better than abstractions.",
        "strategy": "Tell the story of how concepts developed. Name the people, the debates, the moments.",
        "tone": "Story-driven. 'In 1973, Clifford Geertz proposed something radical...'",
        "risk": "May conflate the story with the science. Distinguish narrative from evidence.",
    },
}


# ─── Misconception Remediation ──────────────────────────────────────────────

REMEDIATION_STRATEGIES = {
    "oversimplification": {
        "detection": "Student states a nuanced concept as a simple binary or absolute",
        "approach": "Acknowledge the kernel of truth, then introduce the nuance",
        "template": "You're on the right track — {concept} does involve {simple_version}. But there's an important nuance: {nuance}. Here's why that matters: {consequence}.",
    },
    "false_equivalence": {
        "detection": "Student equates two related but distinct concepts",
        "approach": "Validate the connection, then clarify the distinction",
        "template": "Great instinct connecting {concept_a} and {concept_b} — they are related. The key difference is: {distinction}. Think of it this way: {analogy}.",
    },
    "anachronism": {
        "detection": "Student applies modern concepts to historical contexts",
        "approach": "Show the historical context without judgment",
        "template": "That's a natural way to think about it from today's perspective. But in {time_period}, the context was different: {context}. What {thinker} actually meant was: {meaning}.",
    },
    "authority_confusion": {
        "detection": "Student treats one influential paper as the definitive truth",
        "approach": "Acknowledge the paper's importance, show the broader landscape",
        "template": "{paper} is indeed foundational. But the field has evolved: {evolution}. Today, most researchers see it as {current_view}.",
    },
    "correlation_causation": {
        "detection": "Student infers causation from observed correlation",
        "approach": "Show the distinction with a concrete example",
        "template": "The connection you noticed between {a} and {b} is real — they do co-occur. But the evidence for causation is {strength}. Alternative explanations include: {alternatives}.",
    },
}


# ─── Teaching Moment Detection ──────────────────────────────────────────────

TEACHABLE_MOMENTS = {
    "prerequisite_gap": {
        "trigger": "Student asks about concept X but doesn't know prerequisite Y",
        "response": "Gently redirect: 'Great question about X. To really understand it, let's first make sure we're solid on Y, which is the foundation.'",
    },
    "connection_opportunity": {
        "trigger": "Student is learning X, and they previously learned Y which connects",
        "response": "Bridge: 'Remember when we talked about Y? Here's something cool — X actually {relationship} Y because {explanation}.'",
    },
    "depth_readiness": {
        "trigger": "Student demonstrates solid understanding of a concept (answers quiz correctly, asks sophisticated questions)",
        "response": "Advance: 'You've got a solid grasp of this. Ready for the nuance? {deeper_point}'",
    },
    "struggle_detected": {
        "trigger": "Student gives wrong quiz answer, asks to re-explain, or says 'I don't get it'",
        "response": "Simplify: Drop one depth level, use a different analogy, try a different concept type strategy.",
    },
    "interest_spike": {
        "trigger": "Student asks follow-up questions, clicks related concepts, stays on topic",
        "response": "Feed the interest: Offer related concepts, deeper resources, or a quiz challenge.",
    },
}


# ─── Core Functions ─────────────────────────────────────────────────────────

def get_teaching_strategy(concept_type: str) -> dict:
    """Get the appropriate teaching strategy for a concept type."""
    return CONCEPT_TEACHING_STRATEGIES.get(concept_type, DEFAULT_STRATEGY)


def get_learning_profile(profile_name: str) -> dict:
    """Get a learning profile's teaching adjustments."""
    return LEARNING_PROFILES.get(profile_name, LEARNING_PROFILES["explorer"])


async def detect_student_profile(user_id: str) -> str:
    """Detect the student's learning profile from their behavior data.

    Analyzes: question patterns, topic switching rate, depth of follow-ups,
    evidence requests, and interaction style.
    """
    client = get_client()

    try:
        profile = client.table("user_profiles").select(
            "behavior_data"
        ).eq("user_id", user_id).execute()

        if not profile.data or not profile.data[0].get("behavior_data"):
            return "explorer"  # default

        behavior = profile.data[0]["behavior_data"]
        sessions = behavior.get("sessions", [])

        if len(sessions) < 3:
            return "explorer"  # not enough data

        # Analyze patterns
        avg_msg_len = sum(s.get("msg_len", 0) for s in sessions) / len(sessions)
        concept_counts = [s.get("concepts", 0) for s in sessions]
        avg_concepts = sum(concept_counts) / len(concept_counts) if concept_counts else 0
        modes = [s.get("mode", "") for s in sessions]
        tutor_ratio = modes.count("tutor") / len(modes) if modes else 0

        # Heuristic classification
        if avg_msg_len > 200 and tutor_ratio > 0.3:
            return "deep_diver"
        elif avg_concepts > 3:
            return "explorer"
        elif avg_msg_len < 80:
            return "practical"
        elif tutor_ratio > 0.5:
            return "skeptic"
        else:
            return "explorer"

    except Exception as e:
        logger.warning(f"Profile detection failed: {e}")
        return "explorer"


def build_teaching_context(
    concept_type: str,
    student_profile: str,
    concept_name: str,
    mode: str = "navigator",
    related_concepts: list[str] | None = None,
    student_knows: list[str] | None = None,
    misconceptions: list[str] | None = None,
) -> str:
    """Build a pedagogical instruction block to inject into Claude prompts.

    CRITICAL: In navigator mode, this is MINIMAL — just tone and student context.
    Full teaching instructions only inject in tutor mode.
    Research: default must be "peer", not "teacher" (Baylor & Kim 2005).
    """
    strategy = get_teaching_strategy(concept_type)
    profile = get_learning_profile(student_profile)

    lines = []

    # ── Navigator mode: lightweight peer context ──
    if mode != "tutor":
        lines.append("=== CONVERSATION CONTEXT ===")
        lines.append("")
        lines.append("IMPORTANT: You are a knowledgeable COLLEAGUE, not a teacher.")
        lines.append("Talk at eye level. Be direct. No hollow praise ('Great question!').")
        lines.append("Share knowledge like a peer who happens to know more about this topic.")
        lines.append("If something is debated — say so directly with both sides.")
        lines.append("")

        if student_knows:
            lines.append(f"USER ALREADY KNOWS: {', '.join(student_knows[:10])}")
            lines.append("  → Don't explain these. Reference them as shared knowledge.")
            lines.append("")

        if related_concepts:
            lines.append(f"RELATED TOPICS TO WEAVE IN (if natural): {', '.join(related_concepts[:5])}")
            lines.append("")

        lines.append("=== END CONTEXT ===")
        return "\n".join(lines)

    # ── Tutor mode: full pedagogical instructions ──
    lines.append("=== TEACHING INSTRUCTIONS (Tutor Mode) ===")
    lines.append("")
    lines.append(f"CONCEPT TYPE: {concept_type}")
    lines.append(f"TEACHING APPROACH: {strategy['approach']}")
    lines.append(f"STRATEGY: {strategy['description']}")
    lines.append("")
    lines.append("STEPS:")

    for i, step in enumerate(strategy["steps"], 1):
        lines.append(f"  {i}. {step}")

    lines.append("")
    lines.append("AVOID:")
    for mistake in strategy["common_mistakes"]:
        lines.append(f"  - {mistake}")
    # Research-backed additions
    lines.append("  - Starting with praise ('Great question!', 'Fascinating topic!')")
    lines.append("  - Explaining things the student already knows (expertise reversal effect)")
    lines.append("  - Asking more than 1 question per response unless student is deeply engaged")
    lines.append("  - Hedging ('This might be complex...') — just explain directly")

    lines.append("")
    lines.append(f"ANALOGY: {strategy.get('analogy_prompt', '')}")

    lines.append("")
    lines.append(f"STUDENT PROFILE: {student_profile}")
    lines.append(f"  {profile['strategy']}")
    lines.append(f"  TONE: {profile['tone']}")

    if student_knows:
        lines.append("")
        lines.append(f"STUDENT ALREADY KNOWS: {', '.join(student_knows[:10])}")
        lines.append("  → Skip basics for these. Build bridges to new concept.")
        lines.append("  → If they reference these, match their level immediately.")

    if related_concepts:
        lines.append("")
        lines.append(f"RELATED CONCEPTS (from graph): {', '.join(related_concepts[:5])}")
        lines.append("  → Use these for genuine prompts: 'How does X connect to Y?'")
        lines.append("  → Only ask if the connection EXISTS in the graph.")

    if misconceptions:
        lines.append("")
        lines.append("KNOWN MISCONCEPTIONS:")
        for m in misconceptions[:3]:
            lines.append(f"  - {m}")
        lines.append("  → Address directly: 'Actually, the evidence shows...'")

    lines.append("")
    lines.append("FRUSTRATION SIGNALS (drop to direct mode immediately):")
    lines.append("  - Short responses ('ok', 'sure', 'I see')")
    lines.append("  - Repeated same question")
    lines.append("  - 'just tell me', 'I know', 'skip this'")
    lines.append("  - If detected: give the answer directly, then offer depth.")
    lines.append("")
    lines.append("=== END TEACHING INSTRUCTIONS ===")

    return "\n".join(lines)


async def get_student_knowledge(user_id: str, limit: int = 20) -> list[str]:
    """Get list of concept names the student already knows (understanding > 0.3)."""
    client = get_client()
    try:
        knowledge = client.table("user_knowledge").select(
            "concept_id, understanding_level"
        ).eq("user_id", user_id).gt(
            "understanding_level", 0.3
        ).order("understanding_level", desc=True).limit(limit).execute()

        if not knowledge.data:
            return []

        concept_ids = [k["concept_id"] for k in knowledge.data]
        concepts = client.table("concepts").select("name").in_("id", concept_ids).execute()
        return [c["name"] for c in (concepts.data or [])]
    except Exception:
        return []


async def get_student_misconceptions(user_id: str, concept_id: str) -> list[str]:
    """Get known misconceptions for a student on a specific concept."""
    client = get_client()
    try:
        knowledge = client.table("user_knowledge").select(
            "misconceptions"
        ).eq("user_id", user_id).eq("concept_id", concept_id).execute()

        if not knowledge.data:
            return []

        misconceptions = knowledge.data[0].get("misconceptions") or []
        return [m.get("misconception", "") for m in misconceptions if not m.get("corrected")]
    except Exception:
        return []
