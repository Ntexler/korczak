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

            # Re-embed: a changed definition must refresh the vector,
            # otherwise semantic search serves the OLD meaning forever
            try:
                concept_row = client.table("concepts").select("name").eq("id", concept_id).execute()
                name = concept_row.data[0]["name"] if concept_row.data else ""
                from backend.integrations.openai_client import get_embedding
                emb = await get_embedding(f"{name}: {content[:500]}")
                client.table("concepts").update({"embedding": emb}).eq("id", concept_id).execute()
            except Exception as embed_err:
                logger.warning(f"Re-embed after approval failed (non-fatal): {embed_err}")

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

    # Learning-from-rejection: record the correction so Chappie remembers.
    # (The 'corrected' learning-log type existed but was never written — audit 1.3.)
    try:
        row = client.table("pending_enrichments").select(
            "concept_name, field, source, content"
        ).eq("id", enrichment_id).execute()
        if row.data:
            e = row.data[0]
            from backend.agents.consciousness import log_learning
            await log_learning(
                entry_type="corrected",
                summary=f"Admin rejected my {e.get('source', '?')} proposal about "
                        f"{e.get('concept_name', '?')}" + (f": {note}" if note else ""),
                concept_name=e.get("concept_name"),
                field=e.get("field"),
                source=e.get("source"),
                confidence=0.2,
                detail=(e.get("content") or "")[:500],
            )
    except Exception as log_err:
        logger.debug(f"Rejection learning-log failed (non-fatal): {log_err}")

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
    """Add a URL for the learning agent to process. URL is SSRF-validated."""
    from backend.core.net_guard import is_safe_url
    safe, reason = is_safe_url(source.url)
    if not safe:
        raise HTTPException(status_code=400, detail=f"URL rejected: {reason}")

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


@router.post("/scout/run")
async def run_source_scout(field: str = Query(default="Anthropology"), limit: int = Query(default=8, le=20)):
    """Send the Source Scout to find verified source leads for a field.

    Leads land in manual_sources as pending — approve them like any source.
    """
    from backend.agents.source_scout import run_scout
    return await run_scout(field=field, limit_per_source=limit, store=True)


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


# ─── Korczak Consciousness ──────────────────────────────────────────────────

@router.get("/consciousness/log")
async def get_learning_log(
    field: str | None = None,
    hours: int | None = None,
    limit: int = Query(default=20, le=100),
):
    """Get Korczak's learning diary."""
    from backend.agents.consciousness import get_recent_learnings
    entries = await get_recent_learnings(field=field, limit=limit, hours=hours)
    return {"entries": entries, "total": len(entries)}


@router.post("/consciousness/reflect")
async def trigger_reflection(
    reflection_type: str = "daily",
    field: str | None = None,
):
    """Trigger Korczak to reflect on what he's learned."""
    from backend.agents.consciousness import generate_reflection
    result = await generate_reflection(reflection_type=reflection_type, field=field)
    return result


@router.get("/consciousness/reflections")
async def list_reflections(field: str | None = None, limit: int = 10):
    """Get past reflections."""
    from backend.agents.consciousness import get_reflections
    return {"reflections": await get_reflections(field=field, limit=limit)}


@router.get("/consciousness/curiosities")
async def list_curiosities(field: str | None = None, limit: int = 10):
    """What is Korczak curious about?"""
    from backend.agents.consciousness import get_curiosities
    return {"curiosities": await get_curiosities(field=field, limit=limit)}


@router.post("/consciousness/curiosity/generate")
async def auto_curiosity(field: str = "Anthropology", limit: int = 5):
    """Let Korczak generate his own questions about a field."""
    from backend.agents.consciousness import auto_generate_curiosities
    questions = await auto_generate_curiosities(field=field, limit=limit)
    return {"generated": questions, "count": len(questions)}


@router.get("/consciousness/voice")
async def proactive_message(user_id: str = "mock-user", field: str | None = None):
    """Does Korczak have something to tell the user proactively?"""
    from backend.agents.consciousness import generate_proactive_message
    msg = await generate_proactive_message(user_id=user_id, field=field)
    return msg or {"message": None}


@router.get("/consciousness/memory/export")
async def export_memory(field: str | None = None):
    """Export Korczak's memory as an Obsidian vault ZIP."""
    from backend.agents.consciousness import export_memory_to_obsidian
    from fastapi.responses import Response

    result = await export_memory_to_obsidian(field=field)
    return Response(
        content=result["zip_bytes"],
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="Korczak_Memory.zip"'},
    )
