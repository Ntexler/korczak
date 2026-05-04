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

    # 1. Source Credibility
    credibility = SOURCE_CREDIBILITY.get(source, SOURCE_CREDIBILITY["unknown"])
    reasons = [f"Source credibility ({source}): {credibility:.1f}"]

    # Boost if has references
    ref_count = len(references) if references else 0
    if ref_count >= 3:
        credibility = min(1.0, credibility + 0.1)
        reasons.append(f"Supported by {ref_count} references (+0.1)")
    elif ref_count == 0 and source not in ("expert", "peer_reviewed"):
        credibility = max(0.1, credibility - 0.1)
        reasons.append("No references provided (-0.1)")

    # 2. Internal Consistency — check against existing knowledge
    consistency = 1.0
    contradicts = []
    supports = []

    if concept_name:
        # Get existing concept
        concept = client.table("concepts").select(
            "id, definition, confidence"
        ).ilike("name", f"%{concept_name}%").limit(1).execute()

        if concept.data:
            existing_def = concept.data[0].get("definition", "")
            existing_conf = concept.data[0].get("confidence", 0.5)
            concept_id = concept.data[0]["id"]

            # Check for contradicting claims in the graph
            existing_claims = client.table("claims").select(
                "claim_text, strength, confidence"
            ).limit(20).execute()

            # Simple keyword overlap check for contradictions
            claim_lower = claim_text.lower()
            negation_words = ["not", "never", "incorrect", "wrong", "false",
                             "contradicts", "disproven", "rejected", "refuted"]

            for ec in (existing_claims.data or []):
                ec_text = (ec.get("claim_text") or "").lower()
                # Check if the new claim negates an existing one
                if any(neg in claim_lower for neg in negation_words):
                    # Check for concept name overlap
                    if concept_name.lower() in ec_text:
                        contradicts.append(ec.get("claim_text", "")[:100])
                        consistency -= 0.2
                        reasons.append(f"Potentially contradicts existing claim")

            # Check relationships for contradictions
            rels = client.table("relationships").select(
                "relationship_type, explanation"
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
