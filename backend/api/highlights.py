"""Highlights API — create, list, and manage text highlights and learning paths."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Models ---

class CreateHighlightRequest(BaseModel):
    user_id: str
    source_type: str
    source_id: str
    highlighted_text: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    annotation: Optional[str] = None
    color: str = "#E8B931"
    concept_ids: list[str] = []
    is_public: bool = False


class UpdateHighlightRequest(BaseModel):
    annotation: Optional[str] = None
    color: Optional[str] = None
    is_public: Optional[bool] = None


class CreateLearningPathRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    is_public: bool = False
    domain: Optional[str] = None


class AddPathItemRequest(BaseModel):
    item_type: str
    item_id: str
    position: Optional[int] = None
    annotation: Optional[str] = None


# --- Highlights ---

@router.post("/")
async def create_highlight(req: CreateHighlightRequest):
    """Create a new highlight."""
    try:
        client = get_client()
        data = {
            "user_id": req.user_id,
            "source_type": req.source_type,
            "source_id": req.source_id,
            "highlighted_text": req.highlighted_text,
            "start_offset": req.start_offset,
            "end_offset": req.end_offset,
            "annotation": req.annotation,
            "color": req.color,
            "concept_ids": req.concept_ids,
            "is_public": req.is_public,
        }
        result = client.table("highlights").insert(data).execute()
        return result.data[0] if result.data else {"status": "created"}
    except Exception as e:
        logger.error(f"Create highlight error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_highlights(
    user_id: str = Query(...),
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List user's highlights, optionally filtered by source."""
    try:
        client = get_client()
        query = client.table("highlights").select("*").eq("user_id", user_id)
        if source_type:
            query = query.eq("source_type", source_type)
        if source_id:
            query = query.eq("source_id", source_id)
        query = query.order("created_at", desc=True).limit(limit)
        result = query.execute()
        return {"highlights": result.data or []}
    except Exception as e:
        logger.error(f"List highlights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{highlight_id}")
async def update_highlight(highlight_id: str, req: UpdateHighlightRequest):
    """Update a highlight's annotation or visibility."""
    try:
        client = get_client()
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = client.table("highlights").update(data).eq("id", highlight_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Highlight not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update highlight error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{highlight_id}")
async def delete_highlight(highlight_id: str):
    """Delete a highlight."""
    try:
        client = get_client()
        client.table("highlights").delete().eq("id", highlight_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete highlight error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public")
async def public_highlights(
    source_type: str = Query(...),
    source_id: str = Query(...),
    limit: int = Query(default=20, le=100),
):
    """Get public highlights for a source (for community feature)."""
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


# --- Learning Paths ---

@router.post("/paths")
async def create_learning_path(req: CreateLearningPathRequest):
    """Create a new learning path."""
    try:
        client = get_client()
        data = {
            "user_id": req.user_id,
            "title": req.title,
            "description": req.description,
            "is_public": req.is_public,
            "domain": req.domain,
        }
        result = client.table("learning_paths").insert(data).execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Create path error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paths")
async def list_learning_paths(user_id: str = Query(...)):
    """List user's learning paths."""
    try:
        client = get_client()
        result = (
            client.table("learning_paths")
            .select("*, learning_path_items(count)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"paths": result.data or []}
    except Exception as e:
        logger.error(f"List paths error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paths/{path_id}")
async def get_learning_path(path_id: str):
    """Get a learning path with its items."""
    try:
        client = get_client()
        path = client.table("learning_paths").select("*").eq("id", path_id).execute()
        if not path.data:
            raise HTTPException(status_code=404, detail="Learning path not found")

        items = (
            client.table("learning_path_items")
            .select("*")
            .eq("learning_path_id", path_id)
            .order("position")
            .execute()
        )
        return {**path.data[0], "items": items.data or []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get path error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/paths/{path_id}")
async def delete_learning_path(path_id: str):
    """Delete a learning path."""
    try:
        client = get_client()
        client.table("learning_path_items").delete().eq("learning_path_id", path_id).execute()
        client.table("learning_paths").delete().eq("id", path_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete path error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paths/{path_id}/items")
async def add_path_item(path_id: str, req: AddPathItemRequest):
    """Add an item to a learning path."""
    try:
        client = get_client()
        if req.position is None:
            existing = (
                client.table("learning_path_items")
                .select("position")
                .eq("learning_path_id", path_id)
                .order("position", desc=True)
                .limit(1)
                .execute()
            )
            pos = (existing.data[0]["position"] + 1) if existing.data else 0
        else:
            pos = req.position

        result = client.table("learning_path_items").insert({
            "learning_path_id": path_id,
            "item_type": req.item_type,
            "item_id": req.item_id,
            "position": pos,
            "annotation": req.annotation,
        }).execute()
        return result.data[0] if result.data else {"status": "added"}
    except Exception as e:
        logger.error(f"Add path item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/paths/{path_id}/items/{item_id}")
async def remove_path_item(path_id: str, item_id: str):
    """Remove an item from a learning path."""
    try:
        client = get_client()
        client.table("learning_path_items").delete().eq("id", item_id).eq(
            "learning_path_id", path_id
        ).execute()
        return {"status": "removed"}
    except Exception as e:
        logger.error(f"Remove path item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
