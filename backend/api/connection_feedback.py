"""Connection Feedback API — agree/disagree with connections, propose new ones."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


class FeedbackRequest(BaseModel):
    feedback_type: str  # agree, disagree, suggest_alternative, report_missing
    comment: str | None = None
    suggested_connection: dict | None = None


class ProposedConnectionRequest(BaseModel):
    source_concept_id: str
    target_concept_id: str
    relationship_type: str
    explanation: str


class VoteRequest(BaseModel):
    vote: str  # up, down


# --- Feedback on existing connections ---

@router.post("/{relationship_id}/feedback")
async def submit_feedback(
    relationship_id: str,
    request: FeedbackRequest,
    user_id: str | None = Query(default=None),
):
    """Submit agree/disagree feedback on a connection."""
    try:
        client = get_client()

        # Verify relationship exists
        rel = (
            client.table("relationships")
            .select("id")
            .eq("id", relationship_id)
            .execute()
        )
        if not rel.data:
            raise HTTPException(status_code=404, detail="Relationship not found")

        # Upsert feedback (one per user per relationship per type)
        data = {
            "relationship_id": relationship_id,
            "feedback_type": request.feedback_type,
            "comment": request.comment,
            "suggested_connection": request.suggested_connection,
        }
        if user_id:
            data["user_id"] = user_id

        result = client.table("connection_feedback").upsert(
            data,
            on_conflict="relationship_id,user_id,feedback_type",
        ).execute()

        # If enough disagrees, lower confidence
        await _update_connection_confidence(client, relationship_id)

        return {"status": "ok", "feedback": result.data[0] if result.data else data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Submit feedback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{relationship_id}/feedback")
async def get_feedback(relationship_id: str):
    """Get community feedback on a connection."""
    try:
        client = get_client()

        feedback = (
            client.table("connection_feedback")
            .select("id, feedback_type, comment, created_at")
            .eq("relationship_id", relationship_id)
            .order("created_at", desc=True)
            .execute()
        )

        # Aggregate counts
        agrees = sum(1 for f in feedback.data if f["feedback_type"] == "agree")
        disagrees = sum(1 for f in feedback.data if f["feedback_type"] == "disagree")
        total = agrees + disagrees

        return {
            "relationship_id": relationship_id,
            "agrees": agrees,
            "disagrees": disagrees,
            "consensus": round(agrees / total, 2) if total > 0 else None,
            "total_feedback": len(feedback.data),
            "comments": [
                f for f in feedback.data if f.get("comment")
            ],
        }
    except Exception as e:
        logger.error(f"Get feedback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Propose missing connections ---

@router.post("/propose")
async def propose_connection(
    request: ProposedConnectionRequest,
    user_id: str | None = Query(default=None),
):
    """Propose a missing connection between two concepts."""
    try:
        client = get_client()

        # Verify both concepts exist
        source = client.table("concepts").select("id, name").eq("id", request.source_concept_id).execute()
        target = client.table("concepts").select("id, name").eq("id", request.target_concept_id).execute()
        if not source.data or not target.data:
            raise HTTPException(status_code=404, detail="One or both concepts not found")

        data = {
            "source_concept_id": request.source_concept_id,
            "target_concept_id": request.target_concept_id,
            "relationship_type": request.relationship_type,
            "explanation": request.explanation,
        }
        if user_id:
            data["user_id"] = user_id

        result = client.table("proposed_connections").insert(data).execute()

        return {
            "status": "proposed",
            "proposal": result.data[0] if result.data else data,
            "source_name": source.data[0]["name"],
            "target_name": target.data[0]["name"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Propose connection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals")
async def list_proposals(
    status: str = Query(default="pending"),
    limit: int = Query(default=20, le=100),
):
    """List proposed connections."""
    try:
        client = get_client()

        result = (
            client.table("proposed_connections")
            .select("*, concepts!proposed_connections_source_concept_id_fkey(name), concepts!proposed_connections_target_concept_id_fkey(name)")
            .eq("status", status)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return {"proposals": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error(f"List proposals error: {e}", exc_info=True)
        # Fallback without joins if foreign key names don't match
        try:
            client = get_client()
            result = (
                client.table("proposed_connections")
                .select("*")
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return {"proposals": result.data or [], "count": len(result.data or [])}
        except Exception as e2:
            logger.error(f"List proposals fallback error: {e2}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e2))


@router.post("/proposals/{proposal_id}/vote")
async def vote_proposal(proposal_id: str, request: VoteRequest):
    """Upvote or downvote a proposed connection."""
    try:
        client = get_client()

        proposal = (
            client.table("proposed_connections")
            .select("id, upvotes, downvotes")
            .eq("id", proposal_id)
            .execute()
        )
        if not proposal.data:
            raise HTTPException(status_code=404, detail="Proposal not found")

        current = proposal.data[0]
        if request.vote == "up":
            client.table("proposed_connections").update(
                {"upvotes": current["upvotes"] + 1}
            ).eq("id", proposal_id).execute()
        else:
            client.table("proposed_connections").update(
                {"downvotes": current["downvotes"] + 1}
            ).eq("id", proposal_id).execute()

        return {"status": "voted", "vote": request.vote}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vote proposal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Helpers ---

async def _update_connection_confidence(client, relationship_id: str):
    """Lower connection confidence if many users disagree."""
    feedback = (
        client.table("connection_feedback")
        .select("feedback_type")
        .eq("relationship_id", relationship_id)
        .execute()
    )
    if not feedback.data:
        return

    agrees = sum(1 for f in feedback.data if f["feedback_type"] == "agree")
    disagrees = sum(1 for f in feedback.data if f["feedback_type"] == "disagree")
    total = agrees + disagrees

    if total < 3:
        return  # Not enough feedback to adjust

    # If more than 60% disagree, reduce confidence by 0.1 (min 0.1)
    if disagrees / total > 0.6:
        rel = (
            client.table("relationships")
            .select("confidence")
            .eq("id", relationship_id)
            .execute()
        )
        if rel.data:
            new_confidence = max(0.1, rel.data[0]["confidence"] - 0.1)
            client.table("relationships").update(
                {"confidence": new_confidence}
            ).eq("id", relationship_id).execute()
