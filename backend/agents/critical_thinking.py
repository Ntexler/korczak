"""Critical Thinking Engine — Korczak doesn't believe everything he hears.

When Korczak receives information from ANY source (Sci-Bot, experts, papers,
forums), this module evaluates it critically before accepting it.

Checks:
1. Source Credibility — who said this? peer-reviewed > expert > bot > forum
2. Internal Consistency — does this contradict what I already know?
3. Evidence Quality — empirical > theoretical > anecdotal > opinion
4. Recency — is this based on current or outdated understanding?
5. Consensus — does this align with or challenge the field consensus?

Output: a CriticalAssessment that determines whether to:
- Accept (high confidence, consistent with graph)
- Accept with Note (credible but adds nuance/caveat)
- Flag for Review (contradicts existing knowledge — needs admin)
- Reject (low credibility, no evidence, or logical inconsistency)
"""

import logging
from dataclasses import dataclass, field

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


# Source credibility hierarchy
SOURCE_CREDIBILITY = {
    "peer_reviewed": 1.0,
    "meta_analysis": 0.95,
    "textbook": 0.9,
    "expert": 0.85,
    "scibot": 0.7,       # Full-text grounded but no peer review of the answer
    "multi_search": 0.65, # Abstracts only
    "open_syllabus": 0.6,
    "wikipedia": 0.4,
    "reddit": 0.3,
    "forum": 0.25,
    "blog": 0.2,
    "unknown": 0.1,
}


@dataclass
class CriticalAssessment:
    verdict: str                    # accept, accept_with_note, flag_review, reject
    confidence: float               # 0-1
    credibility_score: float        # source credibility
    consistency_score: float        # how well it fits existing knowledge
    evidence_quality: str           # strong, moderate, weak, anecdotal
    reasons: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)   # concept names that conflict
    supports: list[str] = field(default_factory=list)      # concept names that align
    notes: str = ""


async def evaluate_claim(
    claim_text: str,
    source: str,
    field_name: str | None = None,
    concept_name: str | None = None,
    references: list[dict] | None = None,
) -> CriticalAssessment:
    """Critically evaluate a piece of information before accepting it.

    This is Korczak's "bullshit detector" — applied to EVERYTHING that
    comes in, regardless of source.
    """
    client = get_client()

    # 1. Source Credibility — base score adjusted by rejection history.
    # A source whose proposals keep getting rejected by the admin loses
    # credibility over time (the learning-from-rejection loop).
    credibility = SOURCE_CREDIBILITY.get(source, SOURCE_CREDIBILITY["unknown"])
    reasons = [f"Source credibility ({source}): {credibility:.1f}"]

    penalty = await _source_rejection_penalty(source)
    if penalty > 0:
        credibility = max(0.05, credibility - penalty)
        reasons.append(f"Rejection-history penalty for {source}: -{penalty:.2f}")

    # Boost if has references
    ref_count = len(references) if references else 0
    if ref_count >= 3:
        credibility = min(1.0, credibility + 0.1)
        reasons.append(f"Supported by {ref_count} references (+0.1)")
    elif ref_count == 0 and source not in ("expert", "peer_reviewed"):
        credibility = max(0.1, credibility - 0.1)
        reasons.append("No references provided (-0.1)")

    # 2. Internal Consistency — SEMANTIC check against this concept's own claims.
    # (The old version compared keywords against 20 random claims from the
    # whole table and never populated `supports` — audit finding 1.1.)
    consistency = 1.0
    contradicts = []
    supports = []

    if concept_name:
        concept = client.table("concepts").select(
            "id, definition, confidence"
        ).ilike("name", f"%{concept_name}%").limit(1).execute()

        if concept.data:
            concept_id = concept.data[0]["id"]

            # Concept-SCOPED claims: this concept's papers → their claims
            existing_claims: list[dict] = []
            try:
                from backend.integrations.supabase_client import (
                    get_papers_for_concept, get_claims_for_papers,
                )
                papers = await get_papers_for_concept(concept_id, limit=10)
                if papers:
                    existing_claims = await get_claims_for_papers(
                        [str(p["id"]) for p in papers], limit=10,
                    )
            except Exception as e:
                logger.debug(f"Concept-scoped claim fetch failed: {e}")

            # Semantic pair-check with a single Haiku call
            if existing_claims:
                verdicts = await _semantic_claim_check(claim_text, existing_claims)
                for idx in verdicts.get("contradicts", []):
                    if 0 <= idx < len(existing_claims):
                        contradicts.append(existing_claims[idx].get("claim_text", "")[:150])
                        consistency -= 0.25
                for idx in verdicts.get("supports", []):
                    if 0 <= idx < len(existing_claims):
                        supports.append(existing_claims[idx].get("claim_text", "")[:150])
                        consistency = min(1.0, consistency + 0.05)
                if contradicts:
                    reasons.append(
                        f"Semantically contradicts {len(contradicts)} existing claim(s) about {concept_name}"
                    )
                if supports:
                    reasons.append(
                        f"Corroborated by {len(supports)} existing claim(s) about {concept_name}"
                    )

            # Known debates on this concept lower certainty, not consistency
            rels = client.table("relationships").select(
                "relationship_type"
            ).eq("source_id", concept_id).eq(
                "relationship_type", "CONTRADICTS"
            ).limit(5).execute()
            if rels.data:
                reasons.append(f"Concept has {len(rels.data)} known contradictions — field is debated")

    consistency = max(0.0, min(1.0, consistency))

    # 3. Evidence Quality Assessment
    evidence_quality = _assess_evidence_quality(claim_text, references)
    reasons.append(f"Evidence quality: {evidence_quality}")

    # 4. Recency Check
    if references:
        years = [r.get("year") for r in references if r.get("year")]
        if years:
            max_year = max(y for y in years if isinstance(y, (int, float)))
            if max_year < 2015:
                reasons.append(f"Based on older literature (most recent: {max_year})")
                credibility = max(0.1, credibility - 0.05)
            elif max_year >= 2023:
                reasons.append("Based on recent literature")
                credibility = min(1.0, credibility + 0.05)

    # 5. Calculate Overall Confidence
    overall = (credibility * 0.4 + consistency * 0.3 +
               _evidence_to_score(evidence_quality) * 0.3)

    # 6. Determine Verdict
    if overall >= 0.7 and not contradicts:
        verdict = "accept"
    elif overall >= 0.5 and not contradicts:
        verdict = "accept_with_note"
    elif contradicts:
        verdict = "flag_review"
        reasons.append(f"Contradicts {len(contradicts)} existing claims — needs human review")
    elif overall < 0.3:
        verdict = "reject"
        reasons.append("Too low confidence across all dimensions")
    else:
        verdict = "flag_review"

    return CriticalAssessment(
        verdict=verdict,
        confidence=round(overall, 2),
        credibility_score=round(credibility, 2),
        consistency_score=round(consistency, 2),
        evidence_quality=evidence_quality,
        reasons=reasons,
        contradicts=contradicts,
        supports=supports,
        notes=f"Evaluated from {source} with {ref_count} references",
    )


# Rejection-history cache: source -> (penalty, computed_at_monotonic)
_penalty_cache: dict[str, tuple[float, float]] = {}
_PENALTY_TTL = 300  # seconds


async def _source_rejection_penalty(source: str) -> float:
    """Credibility penalty from admin rejection history for this source.

    penalty = 0.3 * rejection_rate, requiring >= 3 reviewed proposals.
    Cached 5 minutes. Fail-open to 0.
    """
    import time as _time
    now = _time.monotonic()
    cached = _penalty_cache.get(source)
    if cached and now - cached[1] < _PENALTY_TTL:
        return cached[0]

    penalty = 0.0
    try:
        client = get_client()
        rows = client.table("pending_enrichments").select(
            "status"
        ).eq("source", source).in_("status", ["approved", "rejected"]).limit(200).execute()
        reviewed = rows.data or []
        if len(reviewed) >= 3:
            rejected = sum(1 for r in reviewed if r["status"] == "rejected")
            penalty = round(0.3 * (rejected / len(reviewed)), 2)
    except Exception as e:
        logger.debug(f"Rejection-penalty lookup failed: {e}")

    _penalty_cache[source] = (penalty, now)
    return penalty


async def was_rejected_before(concept_id: str, enrichment_type: str) -> bool:
    """Has the admin already rejected a proposal of this type for this concept?

    Used to suppress re-proposing the same rejected content forever.
    """
    try:
        client = get_client()
        rows = client.table("pending_enrichments").select("id").eq(
            "concept_id", concept_id
        ).eq("enrichment_type", enrichment_type).eq(
            "status", "rejected"
        ).limit(1).execute()
        return bool(rows.data)
    except Exception:
        return False


async def _semantic_claim_check(new_claim: str, existing: list[dict]) -> dict:
    """One Haiku call: does the new claim contradict or support each existing claim?

    Returns {"contradicts": [indices], "supports": [indices]}. Empty on failure
    (fail-open to 'unrelated' — never fabricates a contradiction).
    """
    lines = [
        f"{i}. {(c.get('claim_text') or '')[:200]}"
        for i, c in enumerate(existing[:10])
    ]
    prompt = (
        "Compare a NEW claim against EXISTING claims about the same concept.\n\n"
        f"NEW CLAIM: {new_claim[:400]}\n\n"
        "EXISTING CLAIMS:\n" + "\n".join(lines) + "\n\n"
        "For each existing claim decide: does the NEW claim CONTRADICT it "
        "(they cannot both be true), SUPPORT it (they assert compatible/"
        "overlapping propositions), or is it UNRELATED?\n"
        'Return ONLY JSON: {"contradicts": [indices], "supports": [indices]}'
    )
    try:
        import json as _json
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude

        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=200, temperature=0.0)
        text = resp.text
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        start, end = text.find("{"), text.rfind("}")
        parsed = _json.loads(text[start:end + 1])
        return {
            "contradicts": [int(i) for i in parsed.get("contradicts", []) if isinstance(i, (int, float, str)) and str(i).isdigit()],
            "supports": [int(i) for i in parsed.get("supports", []) if isinstance(i, (int, float, str)) and str(i).isdigit()],
        }
    except Exception as e:
        logger.debug(f"Semantic claim check failed (treating as unrelated): {e}")
        return {}


def _assess_evidence_quality(claim: str, references: list[dict] | None) -> str:
    """Assess the quality of evidence supporting a claim."""
    if not references:
        return "anecdotal"

    ref_count = len(references)
    has_doi = any(r.get("doi") for r in references)
    has_year = any(r.get("year") for r in references)

    if ref_count >= 5 and has_doi:
        return "strong"
    elif ref_count >= 2 and (has_doi or has_year):
        return "moderate"
    elif ref_count >= 1:
        return "weak"
    return "anecdotal"


def _evidence_to_score(quality: str) -> float:
    return {"strong": 0.9, "moderate": 0.6, "weak": 0.3, "anecdotal": 0.1}.get(quality, 0.1)


async def evaluate_and_log(
    claim_text: str,
    source: str,
    concept_name: str | None = None,
    field_name: str | None = None,
    references: list[dict] | None = None,
) -> CriticalAssessment:
    """Evaluate AND log the assessment to the learning log."""
    assessment = await evaluate_claim(
        claim_text=claim_text,
        source=source,
        field_name=field_name,
        concept_name=concept_name,
        references=references,
    )

    # Log to learning log
    from backend.agents.consciousness import log_learning

    if assessment.verdict == "accept":
        await log_learning(
            entry_type="confirmed" if assessment.supports else "discovered",
            summary=f"Accepted from {source}: {claim_text[:150]}",
            concept_name=concept_name,
            field=field_name,
            source=source,
            confidence=assessment.confidence,
        )
    elif assessment.verdict == "flag_review":
        if assessment.contradicts:
            await log_learning(
                entry_type="contradicted",
                summary=f"Found contradiction from {source}: {claim_text[:100]} vs existing knowledge",
                concept_name=concept_name,
                field=field_name,
                source=source,
                confidence=assessment.confidence,
                detail=f"Contradicts: {'; '.join(assessment.contradicts[:3])}",
            )
        else:
            await log_learning(
                entry_type="discovered",
                summary=f"Flagged for review from {source}: {claim_text[:150]}",
                concept_name=concept_name,
                field=field_name,
                source=source,
                confidence=assessment.confidence,
            )

    return assessment
