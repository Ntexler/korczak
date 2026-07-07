"""Consensus Engine — only agreed knowledge becomes Korczak's base.

The rule: Korczak's foundational knowledge must be ACADEMICALLY agreed upon.

Tier rules per concept:
- consensus:  3+ academic papers back it, no active contradictions,
              and (Wikipedia corroborates OR confidence >= 0.6)
- contested:  academic sources actively disagree (CONTRADICTS edges
              or contradicting claims exist)
- unverified: definition comes only from a non-academic source
              (e.g. Wikipedia placeholder) with < 2 papers behind it
- emerging:   everything else — academically sourced, not yet enough
              agreement to be "base"

Wikipedia and similar open sources can only VALIDATE (small score boost).
They can never establish consensus on their own.

Downstream effects:
- Chat/synthesis prompts mark non-consensus knowledge explicitly
- The syllabus "Foundations" tier prefers consensus concepts
- Chappie prioritizes contested/emerging concepts for deep dives
"""

import logging

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


def _classify(
    paper_count: int,
    contradiction_count: int,
    definition_source: str,
    confidence: float,
    wiki_validated: bool,
) -> tuple[str, float]:
    """Returns (consensus_status, consensus_score)."""
    # Non-academic base with almost no papers → unverified, full stop
    if definition_source == "wikipedia" and paper_count < 2:
        return "unverified", min(0.2, paper_count * 0.1)

    if contradiction_count > 0:
        # Academic disagreement — visible, valuable, but not base knowledge
        score = min(0.5, paper_count / 20)
        return "contested", round(score, 2)

    # Score: papers are the main signal; wiki only a small boost
    score = min(0.6, paper_count / 10 * 0.6)          # up to 0.6 from papers
    score += 0.2 if confidence >= 0.6 else 0.0         # analysis confidence
    score += 0.2 if wiki_validated else 0.0            # external corroboration

    if paper_count >= 3 and score >= 0.6:
        return "consensus", round(min(score, 1.0), 2)
    return "emerging", round(score, 2)


async def compute_consensus(field: str | None = None, limit: int = 500) -> dict:
    """Recompute consensus tiers for concepts. Run after every seeding/enrichment."""
    client = get_client()

    # Load concepts (optionally scoped to a field via paper subfields)
    concepts = client.table("concepts").select(
        "id, name, paper_count, confidence, definition_source, external_validation"
    ).order("paper_count", desc=True).limit(limit).execute()
    items = concepts.data or []
    if not items:
        return {"updated": 0}

    # Contradiction counts per concept (CONTRADICTS/WEAKENS edges)
    contradictions: dict[str, int] = {}
    rels = client.table("relationships").select(
        "source_id, target_id, relationship_type"
    ).in_("relationship_type", ["CONTRADICTS", "WEAKENS"]).execute()
    for r in (rels.data or []):
        contradictions[r["source_id"]] = contradictions.get(r["source_id"], 0) + 1
        contradictions[r["target_id"]] = contradictions.get(r["target_id"], 0) + 1

    counts = {"consensus": 0, "emerging": 0, "contested": 0, "unverified": 0}
    updated = 0

    for c in items:
        wiki_validated = bool(
            (c.get("external_validation") or {}).get("wikipedia", {}).get("matches")
        )
        status, score = _classify(
            paper_count=c.get("paper_count", 0),
            contradiction_count=contradictions.get(c["id"], 0),
            definition_source=c.get("definition_source") or "paper_analysis",
            confidence=c.get("confidence", 0.5),
            wiki_validated=wiki_validated,
        )
        counts[status] += 1
        prev_status = c.get("consensus_status")
        try:
            client.table("concepts").update({
                "consensus_status": status,
                "consensus_score": score,
            }).eq("id", c["id"]).execute()
            updated += 1
            # Remember the change of mind
            if prev_status and prev_status != status:
                from backend.agents.belief_memory import record_revision
                await record_revision(
                    subject_type="concept", subject_id=c["id"], subject_name=c["name"],
                    old_belief=prev_status, new_belief=status,
                    reason="Evidence balance shifted after new learning.",
                    trigger_source="consensus_recompute", field=field,
                )
        except Exception as e:
            logger.warning(f"Consensus update failed for {c['name']}: {e}")

    logger.info(f"Consensus recomputed: {counts}")
    return {"updated": updated, **counts}


async def get_consensus_summary(field: str | None = None) -> dict:
    """How much of Korczak's knowledge is actually agreed upon?"""
    client = get_client()
    summary = {}
    for status in ("consensus", "emerging", "contested", "unverified"):
        result = client.table("concepts").select(
            "id", count="exact"
        ).eq("consensus_status", status).execute()
        summary[status] = result.count if hasattr(result, "count") and result.count is not None else len(result.data or [])
    total = sum(summary.values()) or 1
    summary["base_knowledge_pct"] = round(summary["consensus"] / total * 100, 1)
    return summary
