"""Admin API — enrichment review, source management, expert connections."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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


# ─── Manual Sources ─────────────────────────────────────────────────────────

class SourceSubmission(BaseModel):
    url: str
    field: str = "Anthropology"
    source_type: str = "url"
    notes: str | None = None


@router.post("/sources/url")
async def add_manual_source(source: SourceSubmission):
    """Add a URL for the learning agent to process."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    result = client.table("manual_sources").insert({
        "url": source.url,
        "field": source.field,
        "source_type": source.source_type,
        "notes": source.notes,
        "status": "pending",
    }).execute()

    return {"status": "added", "id": result.data[0]["id"] if result.data else None}


@router.get("/sources")
async def list_manual_sources(status: str = "pending", limit: int = 20):
    """List manually submitted sources."""
    from backend.integrations.supabase_client import get_client
    client = get_client()
    result = client.table("manual_sources").select("*").eq(
        "status", status
    ).order("created_at", desc=True).limit(limit).execute()
    return {"sources": result.data or []}


# ─── Expert Management ───────────────────────────────────────────────────────

class ExpertCreate(BaseModel):
    name: str
    field: str
    contact_type: str = "whatsapp"
    contact_id: str
    institution: str | None = None
    specialization: str | None = None


@router.post("/experts")
async def create_expert(expert: ExpertCreate):
    """Register a new domain expert."""
    from backend.agents.expert_connector import add_expert
    expert_id = await add_expert(
        name=expert.name,
        field=expert.field,
        contact_type=expert.contact_type,
        contact_id=expert.contact_id,
        institution=expert.institution,
        specialization=expert.specialization,
    )
    return {"status": "created", "expert_id": expert_id}


@router.get("/experts")
async def list_experts(field: str | None = None):
    """List registered experts."""
    from backend.agents.expert_connector import get_experts
    experts = await get_experts(field=field)
    return {"experts": experts}


@router.post("/experts/{expert_id}/ask")
async def ask_expert(
    expert_id: str,
    concept_id: str | None = None,
    question: str | None = None,
):
    """Generate and send a question to an expert."""
    from backend.agents.expert_connector import generate_expert_question
    result = await generate_expert_question(
        expert_id=expert_id,
        concept_id=concept_id,
        custom_question=question,
    )
    return result


@router.post("/experts/conversations/{conv_id}/response")
async def submit_expert_response(conv_id: str, response: str = Query(...)):
    """Submit an expert's response (manual paste or webhook)."""
    from backend.agents.expert_connector import process_expert_response
    result = await process_expert_response(conv_id, response)
    return result
