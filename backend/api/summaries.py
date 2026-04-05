"""Concept Summaries & Discussions API — community-written knowledge interpretations."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSummaryRequest(BaseModel):
    concept_id: str
    author_id: str
    title: str
    body: str
    referenced_concepts: list[str] = []


class UpdateSummaryRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    referenced_concepts: list[str] | None = None
    edit_reason: str | None = None


class CreateDiscussionRequest(BaseModel):
    target_type: str  # concept, relationship, claim, summary, paper
    target_id: str
    author_id: str
    title: str | None = None
    body: str
    parent_id: str | None = None


# --- Concept Summaries ---

@router.get("/concepts/{concept_id}/summaries")
async def list_summaries(
    concept_id: str,
    sort: str = Query(default="top", pattern="^(top|recent)$"),
    limit: int = Query(default=10, le=50),
):
    """Get community summaries for a concept."""
    try:
        client = get_client()
        query = (
            client.table("concept_summaries")
            .select("*, researcher_profiles!concept_summaries_author_id_fkey(display_name, institution)")
            .eq("concept_id", concept_id)
        )
        if sort == "top":
            query = query.order("upvotes", desc=True)
        else:
            query = query.order("created_at", desc=True)

        result = query.limit(limit).execute()
        return {"summaries": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        # Fallback without join
        try:
            client = get_client()
            order_col = "upvotes" if sort == "top" else "created_at"
            result = (
                client.table("concept_summaries")
                .select("*")
                .eq("concept_id", concept_id)
                .order(order_col, desc=True)
                .limit(limit)
                .execute()
            )
            return {"summaries": result.data or [], "count": len(result.data or [])}
        except Exception as e2:
            logger.error(f"List summaries error: {e2}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e2))


@router.post("/summaries")
async def create_summary(request: CreateSummaryRequest):
    """Write a new summary/interpretation for a concept."""
    try:
        client = get_client()
        data = request.model_dump()
        result = client.table("concept_summaries").insert(data).execute()

        summary = result.data[0] if result.data else data

        # Save initial version
        client.table("summary_versions").insert({
            "summary_id": summary.get("id"),
            "version": 1,
            "title": request.title,
            "body": request.body,
        }).execute()

        # Log activity
        client.table("activity_feed").insert({
            "researcher_id": request.author_id,
            "action_type": "wrote_summary",
            "target_type": "concept",
            "target_id": request.concept_id,
            "metadata": {"summary_id": summary.get("id"), "title": request.title},
        }).execute()

        # Boost reputation
        client.table("researcher_profiles").update(
            {"reputation_score": client.table("researcher_profiles").select("reputation_score").eq("id", request.author_id).execute().data[0].get("reputation_score", 0) + 5}
        ).eq("id", request.author_id).execute()

        return summary
    except Exception as e:
        logger.error(f"Create summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/summaries/{summary_id}")
async def update_summary(summary_id: str, request: UpdateSummaryRequest):
    """Edit a summary (creates a new version, preserves history)."""
    try:
        client = get_client()

        # Get current version
        current = client.table("concept_summaries").select("*").eq("id", summary_id).execute()
        if not current.data:
            raise HTTPException(status_code=404, detail="Summary not found")

        old = current.data[0]
        new_version = old.get("version", 1) + 1

        # Update the summary
        update_data = {"version": new_version, "updated_at": "now()"}
        if request.title:
            update_data["title"] = request.title
        if request.body:
            update_data["body"] = request.body
        if request.referenced_concepts is not None:
            update_data["referenced_concepts"] = request.referenced_concepts

        client.table("concept_summaries").update(update_data).eq("id", summary_id).execute()

        # Save version history
        client.table("summary_versions").insert({
            "summary_id": summary_id,
            "version": new_version,
            "title": request.title or old["title"],
            "body": request.body or old["body"],
            "edit_reason": request.edit_reason,
        }).execute()

        # Log activity
        client.table("activity_feed").insert({
            "researcher_id": old["author_id"],
            "action_type": "edited_summary",
            "target_type": "summary",
            "target_id": summary_id,
            "metadata": {"version": new_version, "reason": request.edit_reason},
        }).execute()

        return {"status": "updated", "version": new_version}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summaries/{summary_id}/history")
async def summary_history(summary_id: str):
    """Get edit history of a summary."""
    try:
        client = get_client()
        result = (
            client.table("summary_versions")
            .select("*")
            .eq("summary_id", summary_id)
            .order("version", desc=True)
            .execute()
        )
        return {"versions": result.data or []}
    except Exception as e:
        logger.error(f"Summary history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summaries/{summary_id}/vote")
async def vote_summary(
    summary_id: str,
    voter_id: str = Query(...),
    vote: str = Query(..., pattern="^(up|down)$"),
):
    """Vote on a summary."""
    try:
        client = get_client()

        # Upsert vote
        client.table("summary_votes").upsert(
            {"summary_id": summary_id, "voter_id": voter_id, "vote_type": vote},
            on_conflict="summary_id,voter_id",
        ).execute()

        # Recalculate counts
        ups = client.table("summary_votes").select("id", count="exact").match({"summary_id": summary_id, "vote_type": "up"}).execute()
        downs = client.table("summary_votes").select("id", count="exact").match({"summary_id": summary_id, "vote_type": "down"}).execute()

        client.table("concept_summaries").update({
            "upvotes": ups.count or 0,
            "downvotes": downs.count or 0,
        }).eq("id", summary_id).execute()

        return {"status": "voted", "upvotes": ups.count or 0, "downvotes": downs.count or 0}
    except Exception as e:
        logger.error(f"Vote summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Discussions ---

@router.get("/discussions")
async def list_discussions(
    target_type: str = Query(...),
    target_id: str = Query(...),
    limit: int = Query(default=20, le=100),
):
    """Get discussion threads for a target (concept, relationship, claim, etc.)."""
    try:
        client = get_client()

        # Get top-level discussions (no parent)
        result = (
            client.table("discussions")
            .select("*")
            .eq("target_type", target_type)
            .eq("target_id", target_id)
            .is_("parent_id", "null")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        discussions = result.data or []

        # For each top-level discussion, get replies
        for disc in discussions:
            replies = (
                client.table("discussions")
                .select("*")
                .eq("parent_id", disc["id"])
                .order("created_at")
                .limit(20)
                .execute()
            )
            disc["replies"] = replies.data or []

        return {"discussions": discussions, "count": len(discussions)}
    except Exception as e:
        logger.error(f"List discussions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discussions")
async def create_discussion(request: CreateDiscussionRequest):
    """Start a new discussion or reply to one."""
    try:
        client = get_client()
        data = request.model_dump(exclude_none=True)
        result = client.table("discussions").insert(data).execute()

        disc = result.data[0] if result.data else data

        # Log activity
        action = "replied_discussion" if request.parent_id else "started_discussion"
        client.table("activity_feed").insert({
            "researcher_id": request.author_id,
            "action_type": action,
            "target_type": request.target_type,
            "target_id": request.target_id,
            "metadata": {"discussion_id": disc.get("id"), "title": request.title},
        }).execute()

        # Boost reputation
        rep_result = client.table("researcher_profiles").select("reputation_score").eq("id", request.author_id).execute()
        if rep_result.data:
            client.table("researcher_profiles").update(
                {"reputation_score": rep_result.data[0].get("reputation_score", 0) + 2}
            ).eq("id", request.author_id).execute()

        return disc
    except Exception as e:
        logger.error(f"Create discussion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discussions/{discussion_id}/vote")
async def vote_discussion(
    discussion_id: str,
    voter_id: str = Query(...),
    vote: str = Query(..., pattern="^(up|down)$"),
):
    """Vote on a discussion."""
    try:
        client = get_client()

        client.table("discussion_votes").upsert(
            {"discussion_id": discussion_id, "voter_id": voter_id, "vote_type": vote},
            on_conflict="discussion_id,voter_id",
        ).execute()

        ups = client.table("discussion_votes").select("id", count="exact").match({"discussion_id": discussion_id, "vote_type": "up"}).execute()
        downs = client.table("discussion_votes").select("id", count="exact").match({"discussion_id": discussion_id, "vote_type": "down"}).execute()

        client.table("discussions").update({
            "upvotes": ups.count or 0,
            "downvotes": downs.count or 0,
        }).eq("id", discussion_id).execute()

        return {"status": "voted", "upvotes": ups.count or 0, "downvotes": downs.count or 0}
    except Exception as e:
        logger.error(f"Vote discussion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discussions/{discussion_id}/resolve")
async def resolve_discussion(discussion_id: str):
    """Mark a discussion as resolved."""
    try:
        client = get_client()
        client.table("discussions").update({"is_resolved": True}).eq("id", discussion_id).execute()
        return {"status": "resolved"}
    except Exception as e:
        logger.error(f"Resolve discussion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
