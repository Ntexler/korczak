"""Assessment + Socratic Dialogue Engine.

Two core functions:

1) generate_question(concept) → a targeted question that tests whether the
   learner actually understands the concept — not just has seen it.

2) evaluate_answer(concept, expected_claims, learner_answer) → a grade
   with feedback: correct / partial / incorrect, misconceptions detected,
   a follow-up Socratic prompt, and a suggested mastery delta.

Both use Claude Haiku with structured JSON output, grounded in the
concept's definition + the claims of canonical papers that use the
concept. This keeps evaluation tied to what the graph actually says,
not to Claude's free-form opinion.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

HAIKU_INPUT = 0.80 / 1_000_000
HAIKU_OUTPUT = 4.0 / 1_000_000


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

QUESTION_PROMPT = """You are a tutor probing a learner's real understanding, not their ability to recite.

CONCEPT: {concept_name}
DEFINITION: {definition}
TYPE: {concept_type}
KEY CLAIMS FROM CANONICAL PAPERS:
{claims_block}

Generate ONE assessment question that would reveal whether the learner genuinely grasps this concept. Prefer:
- Application over recall ("given situation X, what would Y predict?")
- Distinguishing from a common near-miss ("how is this different from Z?")
- Evaluating a claim ("is the following true, and why?")

AVOID:
- Trivia (dates, author names)
- Questions that can be answered by repeating the definition verbatim.

Also provide:
- expected_elements: 2-4 key things a correct answer must contain.
- common_misconceptions: 1-3 wrong turns learners often take.

Return JSON only:
{{
  "question": "the single question",
  "question_type": "application|discrimination|claim_evaluation|explanation",
  "expected_elements": ["element 1", "element 2"],
  "common_misconceptions": ["misconception 1", "misconception 2"],
  "difficulty": "easy|medium|hard"
}}
"""


EVAL_PROMPT = """You are evaluating a learner's answer. Ground your evaluation in the concept's definition and in the canonical claims below — not in your own free opinion.

CONCEPT: {concept_name}
DEFINITION: {definition}
KEY CLAIMS:
{claims_block}

QUESTION ASKED: {question}
EXPECTED ELEMENTS (must be covered for full credit): {expected_elements}
COMMON MISCONCEPTIONS: {misconceptions}

LEARNER ANSWER:
\"\"\"{answer}\"\"\"

Evaluate:
1. Which expected elements did the learner cover? Which did they miss?
2. Did they fall into any common misconception?
3. Is their answer correct, partially correct, or incorrect overall?
4. A Socratic follow-up — a single question that would push them to fill the gap WITHOUT revealing the answer.
5. mastery_delta: a number in [-0.2, +0.3] — how much their demonstrated understanding should shift their mastery score.

Return JSON only:
{{
  "verdict": "correct|partial|incorrect",
  "elements_covered": ["..."],
  "elements_missed": ["..."],
  "misconception_detected": "misconception string" | null,
  "feedback": "2-3 sentence direct feedback",
  "socratic_followup": "a single question that pushes them forward without giving the answer",
  "mastery_delta": float
}}
"""


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

async def _call_haiku(prompt: str, max_tokens: int = 1500) -> Optional[dict]:
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
            if r.status_code != 200:
                logger.warning("Haiku %s: %s", r.status_code, r.text[:200])
                return None
            text = r.json()["content"][0]["text"]
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
    except Exception:
        logger.exception("Haiku call failed")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_question(concept: dict, claims: list[dict]) -> Optional[dict]:
    """Generate an assessment question for a concept.

    Args:
      concept: dict with keys id, name, definition, type.
      claims: list of dicts with keys claim_text, strength, evidence_type.
    """
    claims_block = "\n".join(
        f"  - ({c.get('strength','?')}/{c.get('evidence_type','?')}) {c.get('claim_text','')[:200]}"
        for c in claims[:6]
    ) or "  (no canonical claims available — use the definition as anchor)"
    prompt = QUESTION_PROMPT.format(
        concept_name=concept.get("name", ""),
        definition=concept.get("definition") or "(no definition)",
        concept_type=concept.get("type", ""),
        claims_block=claims_block,
    )
    return await _call_haiku(prompt, max_tokens=800)


async def evaluate_answer(
    concept: dict,
    question_obj: dict,
    claims: list[dict],
    answer: str,
) -> Optional[dict]:
    """Evaluate a learner's answer with grounded Socratic feedback.

    question_obj is the output of generate_question (it carries
    expected_elements + common_misconceptions + question).
    """
    claims_block = "\n".join(
        f"  - {c.get('claim_text','')[:200]}"
        for c in claims[:6]
    ) or "  (none)"
    prompt = EVAL_PROMPT.format(
        concept_name=concept.get("name", ""),
        definition=concept.get("definition") or "(no definition)",
        claims_block=claims_block,
        question=question_obj.get("question", ""),
        expected_elements=json.dumps(question_obj.get("expected_elements", []), ensure_ascii=False),
        misconceptions=json.dumps(question_obj.get("common_misconceptions", []), ensure_ascii=False),
        answer=(answer or "").strip()[:2000],
    )
    return await _call_haiku(prompt, max_tokens=1200)


def clamp_delta(delta: float) -> float:
    """Keep mastery changes bounded."""
    try:
        d = float(delta)
    except Exception:
        return 0.0
    if d < -0.2:
        return -0.2
    if d > 0.3:
        return 0.3
    return d
