"""Community API — comments, voting, and public highlights."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Models ---

class CreateCommentRequest(BaseModel):
    paper_id: str
    user_id: str
    content: str
    parent_id: Optional[str] = None


class UpdateCommentRequest(BaseModel):
    content: str


class VoteRequest(BaseModel):
    user_id: str
    target_type: str
    target_id: str
    vote_type: str  # upvote, downvote, flag


# --- Comments ---

@router.post("/comments")
async def create_comment(req: CreateCommentRequest):
    """Create a comment on a paper."""
    try:
        client = get_client()
        data = {
            "paper_id": req.paper_id,
            "user_id": req.user_id,
            "content": req.content,
        }
        if req.parent_id:
            data["parent_id"] = req.parent_id
        result = client.table("paper_comments").insert(data).execute()
        return result.data[0] if result.data else {"status": "created"}
    except Exception as e:
        logger.error(f"Create comment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments")
async def list_comments(
    paper_id: str = Query(...),
    limit: int = Query(default=50, le=200),
):
    """List threaded comments for a paper."""
    try:
        client = get_client()
        result = (
            client.table("paper_comments")
            .select("*")
            .eq("paper_id", paper_id)
            .eq("is_hidden", False)
            .order("created_at")
            .limit(limit)
            .execute()
        )

        # Build threaded structure
        comments = result.data or []
        by_id = {c["id"]: {**c, "replies": []} for c in comments}
        roots = []

        for c in comments:
            node = by_id[c["id"]]
            if c.get("parent_id") and c["parent_id"] in by_id:
                by_id[c["parent_id"]]["replies"].append(node)
            else:
                roots.append(node)

        return {"comments": roots, "total": len(comments)}
    except Exception as e:
        logger.error(f"List comments error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/comments/{comment_id}")
async def update_comment(comment_id: str, req: UpdateCommentRequest):
    """Edit a comment."""
    try:
        client = get_client()
        result = client.table("paper_comments").update(
            {"content": req.content}
        ).eq("id", comment_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Comment not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update comment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: str):
    """Delete a comment (soft delete — sets is_hidden)."""
    try:
        client = get_client()
        result = client.table("paper_comments").update(
            {"is_hidden": True}
        ).eq("id", comment_id).execute()
        return {"status": "hidden"}
    except Exception as e:
        logger.error(f"Delete comment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Voting ---

@router.post("/vote")
async def vote(req: VoteRequest):
    """Vote on a comment, highlight, or learning path."""
    try:
        client = get_client()

        # Upsert vote (toggle: if same vote exists, remove it)
        existing = (
            client.table("community_votes")
            .select("id, vote_type")
            .eq("user_id", req.user_id)
            .eq("target_type", req.target_type)
            .eq("target_id", req.target_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            old_vote = existing.data[0]
            if old_vote["vote_type"] == req.vote_type:
                # Remove vote (toggle off)
                client.table("community_votes").delete().eq("id", old_vote["id"]).execute()
                _update_vote_counts(req.target_type, req.target_id, req.vote_type, -1)
                return {"status": "removed", "action": "toggle_off"}
            else:
                # Change vote
                client.table("community_votes").update(
                    {"vote_type": req.vote_type}
                ).eq("id", old_vote["id"]).execute()
                _update_vote_counts(req.target_type, req.target_id, old_vote["vote_type"], -1)
                _update_vote_counts(req.target_type, req.target_id, req.vote_type, 1)
                return {"status": "changed", "from": old_vote["vote_type"], "to": req.vote_type}
        else:
            # New vote
            client.table("community_votes").insert({
                "user_id": req.user_id,
                "target_type": req.target_type,
                "target_id": req.target_id,
                "vote_type": req.vote_type,
            }).execute()
            _update_vote_counts(req.target_type, req.target_id, req.vote_type, 1)
            return {"status": "voted", "vote_type": req.vote_type}
    except Exception as e:
        logger.error(f"Vote error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _update_vote_counts(target_type: str, target_id: str, vote_type: str, delta: int):
    """Update vote counts on the target record."""
    client = get_client()
    if target_type == "comment":
        table = "paper_comments"
    else:
        return  # Only comments have denormalized counts

    try:
        # Get current count
        result = client.table(table).select(vote_type + "s").eq("id", target_id).execute()
        if result.data:
            current = result.data[0].get(vote_type + "s", 0)
            client.table(table).update(
                {vote_type + "s": max(0, current + delta)}
            ).eq("id", target_id).execute()
    except Exception as e:
        logger.warning(f"Vote count update failed: {e}")


# --- Public highlights for a source ---

@router.get("/highlights/public")
async def public_highlights_for_source(
    source_type: str = Query(...),
    source_id: str = Query(...),
    limit: int = Query(default=20, le=100),
):
    """Get public highlights for a source (papers, AI responses, etc.)."""
    try:
        client = get_client()
        result = (
            client.table("highlights")
            .select("id, highlighted_text, annotation, color, user_id, created_at")
            .eq("source_type", source_type)
            .eq("source_id", source_id)
            .eq("is_public", True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"highlights": result.data or []}
    except Exception as e:
        logger.error(f"Public highlights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
