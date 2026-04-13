"""Attention Engine — process signals and generate deeper analysis.

When users interact with content (save, rate, flag, import vault), attention
signals are created. This engine processes them to generate insights WITHOUT
changing global scores — it only flags things for deeper investigation and
reports findings back to the user.
"""

import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def create_signal(
    user_id: str,
    signal_type: str,
    direction: str,
    target_type: str,
    target_id: str | None = None,
    target_name: str | None = None,
    context: str | None = None,
) -> dict:
    """Create an attention signal from a user action."""
    client = get_client()

    signal = {
        "user_id": user_id,
        "signal_type": signal_type,
        "direction": direction,
        "target_type": target_type,
        "target_id": target_id,
        "target_name": target_name,
        "context": context,
        "status": "pending",
    }

    result = client.table("attention_signals").insert(signal).execute()
    return result.data[0] if result.data else signal


async def process_signal(signal_id: str) -> dict | None:
    """Process a single attention signal — investigate and generate findings.

    Does NOT change any global scores. Only creates insights.
    """
    client = get_client()

    # Get the signal
    signal = client.table("attention_signals").select("*").eq(
        "id", signal_id
    ).execute()
    if not signal.data:
        return None

    s = signal.data[0]

    # Mark as processing
    client.table("attention_signals").update(
        {"status": "processing"}
    ).eq("id", signal_id).execute()

    try:
        resolution = await _investigate(s)

        # Mark as resolved
        client.table("attention_signals").update({
            "status": "resolved",
            "resolution": resolution,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", signal_id).execute()

        return resolution

    except Exception as e:
        logger.error(f"Failed to process signal {signal_id}: {e}")
        client.table("attention_signals").update(
            {"status": "pending"}
        ).eq("id", signal_id).execute()
        return None


async def _investigate(signal: dict) -> dict:
    """Investigate a signal based on its type and direction."""
    target_type = signal["target_type"]
    target_id = signal.get("target_id")
    direction = signal["direction"]
    signal_type = signal["signal_type"]

    if target_type == "concept" and target_id:
        return await _investigate_concept(target_id, direction, signal_type)
    elif target_type == "paper" and target_id:
        return await _investigate_paper(target_id, direction, signal_type)
    else:
        return {"status": "skipped", "reason": "unsupported target type"}


async def _investigate_concept(
    concept_id: str,
    direction: str,
    signal_type: str,
) -> dict:
    """Investigate a concept — find related evidence, gaps, or conflicts."""
    client = get_client()

    concept = client.table("concepts").select(
        "id, name, type, definition, paper_count, confidence, trend, controversy_score"
    ).eq("id", concept_id).execute()

    if not concept.data:
        return {"status": "not_found"}

    c = concept.data[0]
    findings = {
        "concept": c["name"],
        "current_confidence": c.get("confidence", 0),
        "current_trend": c.get("trend", "stable"),
        "investigations": [],
    }

    # Get related papers
    from backend.integrations.supabase_client import get_papers_for_concept
    papers = await get_papers_for_concept(concept_id, limit=10)

    if direction == "skepticism":
        # Look for contradicting evidence
        rels = client.table("relationships").select(
            "source_id, target_id, relationship_type, explanation"
        ).eq("relationship_type", "CONTRADICTS").execute()

        contradictions = [
            r for r in (rels.data or [])
            if r["source_id"] == concept_id or r["target_id"] == concept_id
        ]

        findings["investigations"].append({
            "type": "contradiction_scan",
            "found": len(contradictions),
            "details": [r["explanation"] for r in contradictions[:5] if r.get("explanation")],
        })

        # Check controversy score
        if c.get("controversy_score", 0) > 0.5:
            findings["investigations"].append({
                "type": "high_controversy",
                "score": c["controversy_score"],
                "note": "This concept has active debate in the literature",
            })

        # Check paper recency — old papers might be outdated
        if papers:
            years = [p.get("publication_year", 0) for p in papers if p.get("publication_year")]
            if years:
                latest = max(years)
                if latest < 2015:
                    findings["investigations"].append({
                        "type": "potentially_outdated",
                        "latest_paper": latest,
                        "note": f"Most recent paper is from {latest} — newer perspectives may exist",
                    })

    elif direction == "interest":
        # Look for extending / building concepts
        rels = client.table("relationships").select(
            "source_id, target_id, relationship_type, explanation, confidence"
        ).execute()

        extensions = [
            r for r in (rels.data or [])
            if (r["source_id"] == concept_id or r["target_id"] == concept_id)
            and r["relationship_type"] in ("EXTENDS", "BUILDS_ON", "APPLIES")
        ]

        findings["investigations"].append({
            "type": "extension_scan",
            "found": len(extensions),
            "details": [r["explanation"] for r in extensions[:5] if r.get("explanation")],
        })

        # Check for recent papers
        if papers:
            recent = [p for p in papers if (p.get("publication_year") or 0) >= 2020]
            if recent:
                findings["investigations"].append({
                    "type": "recent_work",
                    "count": len(recent),
                    "titles": [p.get("title", "") for p in recent[:3]],
                })

    findings["paper_count"] = len(papers)
    findings["status"] = "investigated"

    return findings


async def _investigate_paper(
    paper_id: str,
    direction: str,
    signal_type: str,
) -> dict:
    """Investigate a paper — check citations, related work, potential issues."""
    client = get_client()

    paper = client.table("papers").select(
        "id, title, authors, publication_year, cited_by_count, doi, abstract"
    ).eq("id", paper_id).execute()

    if not paper.data:
        return {"status": "not_found"}

    p = paper.data[0]
    findings = {
        "paper": p["title"],
        "year": p.get("publication_year"),
        "cited_by": p.get("cited_by_count", 0),
        "investigations": [],
    }

    # Get claims from this paper
    claims = client.table("claims").select(
        "claim_text, evidence_type, strength, confidence"
    ).eq("paper_id", paper_id).order("confidence", desc=True).execute()

    if claims.data:
        findings["claims_count"] = len(claims.data)

        if direction == "skepticism":
            weak = [c for c in claims.data if c.get("strength") == "weak"]
            if weak:
                findings["investigations"].append({
                    "type": "weak_claims",
                    "count": len(weak),
                    "examples": [c["claim_text"] for c in weak[:3]],
                })

        findings["investigations"].append({
            "type": "claims_summary",
            "strong": sum(1 for c in claims.data if c.get("strength") == "strong"),
            "moderate": sum(1 for c in claims.data if c.get("strength") == "moderate"),
            "weak": sum(1 for c in claims.data if c.get("strength") == "weak"),
        })

    # Get concepts linked to this paper
    pc = client.table("paper_concepts").select(
        "concept_id, relevance"
    ).eq("paper_id", paper_id).order("relevance", desc=True).execute()

    if pc.data:
        concept_ids = [r["concept_id"] for r in pc.data[:10]]
        concepts = client.table("concepts").select(
            "id, name, type"
        ).in_("id", concept_ids).execute()

        findings["related_concepts"] = [c["name"] for c in (concepts.data or [])]

    findings["status"] = "investigated"
    return findings


async def get_user_insights(
    user_id: str,
    include_dismissed: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Get vault insights for a user."""
    client = get_client()

    query = client.table("vault_insights").select("*").eq("user_id", user_id)
    if not include_dismissed:
        query = query.eq("dismissed", False)

    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


async def dismiss_insight(insight_id: str) -> bool:
    """Mark an insight as dismissed."""
    client = get_client()
    client.table("vault_insights").update(
        {"dismissed": True}
    ).eq("id", insight_id).execute()
    return True


async def get_pending_signals(user_id: str, limit: int = 10) -> list[dict]:
    """Get unprocessed attention signals for a user."""
    client = get_client()
    result = client.table("attention_signals").select("*").eq(
        "user_id", user_id
    ).eq("status", "pending").order(
        "created_at", desc=True
    ).limit(limit).execute()
    return result.data or []


async def get_analysis_history(user_id: str, limit: int = 5) -> list[dict]:
    """Get past vault analyses for a user."""
    client = get_client()
    result = client.table("vault_analyses").select("*").eq(
        "user_id", user_id
    ).order("created_at", desc=True).limit(limit).execute()
    return result.data or []
