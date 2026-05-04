"""Admin API — review and approve/reject enrichments from the Learning Agent."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/enrichments")
async def list_pending_enrichments(
    field: str | None = None,
    status: str = "pending",
    limit: int = Query(default=20, le=100),
):
    """List enrichments pending admin review."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    query = client.table("pending_enrichments").select("*").eq("status", status)
    if field:
        query = query.eq("field", field)

    result = query.order("priority", desc=True).order("created_at").limit(limit).execute()
    return {"enrichments": result.data or [], "total": len(result.data or [])}


@router.post("/enrichments/{enrichment_id}/approve")
async def approve_enrichment(
    enrichment_id: str,
    admin_id: str = Query(default="admin"),
    note: str | None = None,
):
    """Approve an enrichment — applies it to the knowledge graph."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    # Get the enrichment
    result = client.table("pending_enrichments").select("*").eq("id", enrichment_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Enrichment not found")

    enrichment = result.data[0]
    concept_id = enrichment["concept_id"]
    etype = enrichment["enrichment_type"]
    content = enrichment["content"]

    # Apply to graph based on type
    try:
        if etype == "definition":
            client.table("concepts").update({
                "definition": content[:500],
            }).eq("id", concept_id).execute()

        elif etype == "claim":
            # Add as a new claim (need a paper_id — use first reference if available)
            refs = enrichment.get("references") or []
            paper_id = None
            if refs and refs[0].get("doi"):
                paper = client.table("papers").select("id").eq("doi", refs[0]["doi"]).execute()
                if paper.data:
                    paper_id = paper.data[0]["id"]

            if paper_id:
                client.table("claims").insert({
                    "paper_id": paper_id,
                    "claim_text": content[:500],
                    "evidence_type": "theoretical",
                    "strength": "moderate",
                    "confidence": 0.5,
                }).execute()

        elif etype == "confidence_update":
            # Store as attention signal for further investigation
            from backend.core.attention_engine import create_signal
            await create_signal(
                user_id=admin_id,
                signal_type="flagged",
                direction="neutral",
                target_type="concept",
                target_id=concept_id,
                target_name=enrichment["concept_name"],
                context=f"Confidence review: {content[:200]}",
            )

        # Mark as approved
        client.table("pending_enrichments").update({
            "status": "approved",
            "reviewed_by": admin_id,
            "review_note": note,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", enrichment_id).execute()

        return {"status": "approved", "enrichment_id": enrichment_id, "type": etype}

    except Exception as e:
        logger.error(f"Failed to apply enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrichments/{enrichment_id}/reject")
async def reject_enrichment(
    enrichment_id: str,
    admin_id: str = Query(default="admin"),
    note: str | None = None,
):
    """Reject an enrichment — does not apply to graph."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    client.table("pending_enrichments").update({
        "status": "rejected",
        "reviewed_by": admin_id,
        "review_note": note,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", enrichment_id).execute()

    return {"status": "rejected", "enrichment_id": enrichment_id}


@router.post("/enrichments/approve-batch")
async def approve_batch(
    ids: list[str] = Query(...),
    admin_id: str = Query(default="admin"),
):
    """Approve multiple enrichments at once."""
    results = []
    for eid in ids:
        try:
            result = await approve_enrichment(eid, admin_id=admin_id)
            results.append(result)
        except Exception as e:
            results.append({"enrichment_id": eid, "status": "error", "error": str(e)})
    return {"results": results}


@router.get("/enrichments/stats")
async def enrichment_stats():
    """Get enrichment queue statistics."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    pending = client.table("pending_enrichments").select("id", count="exact").eq("status", "pending").execute()
    approved = client.table("pending_enrichments").select("id", count="exact").eq("status", "approved").execute()
    rejected = client.table("pending_enrichments").select("id", count="exact").eq("status", "rejected").execute()

    return {
        "pending": pending.count if hasattr(pending, "count") else len(pending.data or []),
        "approved": approved.count if hasattr(approved, "count") else len(approved.data or []),
        "rejected": rejected.count if hasattr(rejected, "count") else len(rejected.data or []),
    }
