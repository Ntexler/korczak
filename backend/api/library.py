"""Library API — save papers, manage reading lists, get recommendations."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client
from backend.core.reading_recommender import get_recommendations

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Models ---

class SavePaperRequest(BaseModel):
    user_id: str
    paper_id: str
    save_context: str = "browsing"
    notes: Optional[str] = None
    tags: list[str] = []


class UpdatePaperRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    rating: Optional[int] = None
    tags: Optional[list[str]] = None


class CreateReadingListRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    is_public: bool = False
    color: str = "#E8B931"
    source_type: str = "manual"
    source_url: Optional[str] = None


class UpdateReadingListRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    color: Optional[str] = None


class AddPaperToListRequest(BaseModel):
    paper_id: str
    position: Optional[int] = None


class ReorderPaperRequest(BaseModel):
    paper_id: str
    new_position: int


# --- User Papers ---

@router.post("/papers")
async def save_paper(req: SavePaperRequest):
    """Save a paper to user's library."""
    try:
        client = get_client()
        data = {
            "user_id": req.user_id,
            "paper_id": req.paper_id,
            "save_context": req.save_context,
            "tags": req.tags,
        }
        if req.notes:
            data["notes"] = req.notes
        result = client.table("user_papers").upsert(
            data, on_conflict="user_id,paper_id"
        ).execute()
        return result.data[0] if result.data else {"status": "saved"}
    except Exception as e:
        logger.error(f"Save paper error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/papers")
async def list_papers(
    user_id: str = Query(...),
    status: Optional[str] = None,
    save_context: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """List user's saved papers with filters."""
    try:
        client = get_client()
        query = (
            client.table("user_papers")
            .select("*, papers(id, title, authors, publication_year, cited_by_count, abstract, doi)")
            .eq("user_id", user_id)
        )
        if status:
            query = query.eq("status", status)
        if save_context:
            query = query.eq("save_context", save_context)
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()

        papers = []
        for row in (result.data or []):
            paper = row.pop("papers", None)
            if paper:
                papers.append({**row, **paper})
            else:
                papers.append(row)
        return {"papers": papers, "total": len(papers)}
    except Exception as e:
        logger.error(f"List papers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/papers/{paper_id}")
async def update_paper(paper_id: str, user_id: str = Query(...), req: UpdatePaperRequest = None):
    """Update a saved paper's status, notes, or rating."""
    try:
        client = get_client()
        data = {}
        if req.status is not None:
            data["status"] = req.status
        if req.notes is not None:
            data["notes"] = req.notes
        if req.rating is not None:
            data["rating"] = req.rating
        if req.tags is not None:
            data["tags"] = req.tags
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = (
            client.table("user_papers")
            .update(data)
            .eq("user_id", user_id)
            .eq("paper_id", paper_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Paper not found in library")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update paper error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/papers/{paper_id}")
async def remove_paper(paper_id: str, user_id: str = Query(...)):
    """Remove a paper from user's library."""
    try:
        client = get_client()
        client.table("user_papers").delete().eq("user_id", user_id).eq("paper_id", paper_id).execute()
        return {"status": "removed"}
    except Exception as e:
        logger.error(f"Remove paper error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/papers/{paper_id}/status")
async def get_paper_status(paper_id: str, user_id: str = Query(...)):
    """Check if a paper is saved and its status."""
    try:
        client = get_client()
        result = (
            client.table("user_papers")
            .select("status, save_context, notes, rating, tags")
            .eq("user_id", user_id)
            .eq("paper_id", paper_id)
            .execute()
        )
        if result.data:
            return {"saved": True, **result.data[0]}
        return {"saved": False}
    except Exception as e:
        logger.error(f"Paper status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Reading Lists ---

@router.post("/lists")
async def create_reading_list(req: CreateReadingListRequest):
    """Create a new reading list."""
    try:
        client = get_client()
        data = {
            "user_id": req.user_id,
            "title": req.title,
            "description": req.description,
            "is_public": req.is_public,
            "color": req.color,
            "source_type": req.source_type,
            "source_url": req.source_url,
        }
        result = client.table("reading_lists").insert(data).execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Create list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lists")
async def list_reading_lists(user_id: str = Query(...)):
    """List user's reading lists."""
    try:
        client = get_client()
        result = (
            client.table("reading_lists")
            .select("*, reading_list_papers(count)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"lists": result.data or []}
    except Exception as e:
        logger.error(f"List reading lists error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lists/{list_id}")
async def get_reading_list(list_id: str):
    """Get a reading list with its papers."""
    try:
        client = get_client()
        # Get the list
        list_result = client.table("reading_lists").select("*").eq("id", list_id).execute()
        if not list_result.data:
            raise HTTPException(status_code=404, detail="Reading list not found")

        # Get papers in order
        papers_result = (
            client.table("reading_list_papers")
            .select("*, papers(id, title, authors, publication_year, cited_by_count, abstract)")
            .eq("reading_list_id", list_id)
            .order("position")
            .execute()
        )

        papers = []
        for row in (papers_result.data or []):
            paper = row.pop("papers", None)
            if paper:
                papers.append({**paper, "position": row["position"]})

        return {**list_result.data[0], "papers": papers}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/lists/{list_id}")
async def update_reading_list(list_id: str, req: UpdateReadingListRequest):
    """Update a reading list."""
    try:
        client = get_client()
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = client.table("reading_lists").update(data).eq("id", list_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Reading list not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lists/{list_id}")
async def delete_reading_list(list_id: str):
    """Delete a reading list."""
    try:
        client = get_client()
        client.table("reading_list_papers").delete().eq("reading_list_id", list_id).execute()
        client.table("reading_lists").delete().eq("id", list_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Papers in Lists ---

@router.post("/lists/{list_id}/papers")
async def add_paper_to_list(list_id: str, req: AddPaperToListRequest):
    """Add a paper to a reading list."""
    try:
        client = get_client()
        # Get next position if not specified
        if req.position is None:
            existing = (
                client.table("reading_list_papers")
                .select("position")
                .eq("reading_list_id", list_id)
                .order("position", desc=True)
                .limit(1)
                .execute()
            )
            next_pos = (existing.data[0]["position"] + 1) if existing.data else 0
        else:
            next_pos = req.position

        result = client.table("reading_list_papers").upsert(
            {"reading_list_id": list_id, "paper_id": req.paper_id, "position": next_pos},
            on_conflict="reading_list_id,paper_id",
        ).execute()
        return result.data[0] if result.data else {"status": "added"}
    except Exception as e:
        logger.error(f"Add to list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lists/{list_id}/papers/{paper_id}")
async def remove_paper_from_list(list_id: str, paper_id: str):
    """Remove a paper from a reading list."""
    try:
        client = get_client()
        client.table("reading_list_papers").delete().eq(
            "reading_list_id", list_id
        ).eq("paper_id", paper_id).execute()
        return {"status": "removed"}
    except Exception as e:
        logger.error(f"Remove from list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/lists/{list_id}/reorder")
async def reorder_paper_in_list(list_id: str, req: ReorderPaperRequest):
    """Reorder a paper within a reading list."""
    try:
        client = get_client()
        client.table("reading_list_papers").update(
            {"position": req.new_position}
        ).eq("reading_list_id", list_id).eq("paper_id", req.paper_id).execute()
        return {"status": "reordered"}
    except Exception as e:
        logger.error(f"Reorder error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Recommendations ---

@router.get("/recommendations")
async def recommendations(
    user_id: str = Query(...),
    limit: int = Query(default=10, le=30),
):
    """Get smart reading recommendations based on saved papers."""
    try:
        return {"recommendations": await get_recommendations(user_id, limit=limit)}
    except Exception as e:
        logger.error(f"Recommendations error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
