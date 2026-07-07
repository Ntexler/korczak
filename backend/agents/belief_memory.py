"""Belief Memory — Korczak's intellectual biography.

No knowledge system remembers the history of its own mind changing.
This one does: "I used to think X was settled; in May 2026 a new paper
made it contested; here's why."

Why it matters:
- Epistemic honesty made visible — the graph carries its own revision log
- A teaching tool: shows learners that changing your mind on evidence is
  an achievement, not a failure
- A research signal: fields where beliefs revise often are the live edges

Recorded automatically when:
- consensus recompute changes a concept's status
- belief propagation demotes a 'consensus' node
- admin reverts an auto-approval
- a proposition's stance balance flips
"""

import logging

logger = logging.getLogger(__name__)


async def record_revision(
    subject_type: str,          # 'concept' | 'proposition'
    subject_id: str | None,
    subject_name: str,
    old_belief: str,
    new_belief: str,
    reason: str,
    trigger_source: str,        # propagation | new_evidence | admin_revert | stance_shift | consensus_recompute
    field: str | None = None,
    trigger_ref: str | None = None,
) -> None:
    """Log a change of mind. Silent no-op on failure — never blocks the caller."""
    if old_belief == new_belief:
        return
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()
        client.table("belief_revisions").insert({
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_name": subject_name,
            "field": field,
            "old_belief": old_belief,
            "new_belief": new_belief,
            "reason": reason,
            "trigger_source": trigger_source,
            "trigger_ref": trigger_ref,
        }).execute()
        logger.info(f"Belief revision [{trigger_source}]: {subject_name} "
                    f"{old_belief} → {new_belief}")

        # Also surface it in Chappie's episodic diary
        from backend.agents.consciousness import log_learning
        await log_learning(
            entry_type="corrected",
            summary=f"I changed my mind about {subject_name}: {old_belief} → "
                    f"{new_belief}. {reason}",
            concept_name=subject_name, field=field,
            source=trigger_source, confidence=0.5,
        )
    except Exception as e:
        logger.debug(f"Belief revision record failed: {e}")


async def get_revisions(field: str | None = None, limit: int = 20) -> list[dict]:
    """Recent changes of mind — the intellectual biography."""
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()
        q = client.table("belief_revisions").select("*")
        if field:
            q = q.eq("field", field)
        rows = q.order("revised_at", desc=True).limit(limit).execute()
        return rows.data or []
    except Exception:
        return []


async def get_subject_history(subject_id: str) -> list[dict]:
    """Full revision history for one concept/proposition — its whole story."""
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()
        rows = client.table("belief_revisions").select("*").eq(
            "subject_id", subject_id
        ).order("revised_at").execute()
        return rows.data or []
    except Exception:
        return []
