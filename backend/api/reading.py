"""Reading API — session tracking, reading behavior analytics, paper sections."""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client
from backend.core.paper_sections import get_paper_sections

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Models ---

class StartSessionRequest(BaseModel):
    user_id: str
    paper_id: str


class UpdateSessionRequest(BaseModel):
    total_seconds: Optional[int] = None
    sections_visited: Optional[list[dict]] = None
    scroll_depth: Optional[float] = None
    concept_focus: Optional[dict] = None


# --- Reading Sessions ---

@router.post("/sessions")
async def start_session(req: StartSessionRequest):
    """Start a new reading session for a paper."""
    try:
        client = get_client()
        result = client.table("reading_sessions").insert({
            "user_id": req.user_id,
            "paper_id": req.paper_id,
        }).execute()
        return result.data[0] if result.data else {"status": "started"}
    except Exception as e:
        logger.error(f"Start session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, req: UpdateSessionRequest):
    """Update a reading session with progress data (called periodically)."""
    try:
        client = get_client()
        data = {}
        if req.total_seconds is not None:
            data["total_seconds"] = req.total_seconds
        if req.sections_visited is not None:
            data["sections_visited"] = req.sections_visited
        if req.scroll_depth is not None:
            data["scroll_depth"] = req.scroll_depth
        if req.concept_focus is not None:
            data["concept_focus"] = req.concept_focus
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = client.table("reading_sessions").update(data).eq("id", session_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Session not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str):
    """End a reading session."""
    try:
        client = get_client()
        result = client.table("reading_sessions").update({
            "ended_at": datetime.utcnow().isoformat(),
        }).eq("id", session_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Session not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"End session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    user_id: str = Query(...),
    paper_id: Optional[str] = None,
    limit: int = Query(default=20, le=100),
):
    """Get reading session history."""
    try:
        client = get_client()
        query = (
            client.table("reading_sessions")
            .select("*, papers(id, title)")
            .eq("user_id", user_id)
        )
        if paper_id:
            query = query.eq("paper_id", paper_id)
        query = query.order("started_at", desc=True).limit(limit)
        result = query.execute()
        return {"sessions": result.data or []}
    except Exception as e:
        logger.error(f"List sessions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def reading_analytics(user_id: str = Query(...)):
    """Get reading behavior summary for a user."""
    try:
        client = get_client()
        sessions = (
            client.table("reading_sessions")
            .select("total_seconds, concept_focus, paper_id, started_at")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(100)
            .execute()
        )

        if not sessions.data:
            return {
                "total_sessions": 0,
                "total_reading_time": 0,
                "avg_session_time": 0,
                "top_concepts": [],
                "papers_read": 0,
            }

        data = sessions.data
        total_time = sum(s.get("total_seconds", 0) for s in data)
        papers_read = len({s["paper_id"] for s in data})

        # Aggregate concept focus across sessions
        concept_times: dict[str, int] = {}
        for s in data:
            focus = s.get("concept_focus") or {}
            for cid, secs in focus.items():
                concept_times[cid] = concept_times.get(cid, 0) + (secs if isinstance(secs, int) else 0)

        # Get concept names for top focused concepts
        top_concept_ids = sorted(concept_times, key=concept_times.get, reverse=True)[:10]
        top_concepts = []
        if top_concept_ids:
            concepts = (
                client.table("concepts")
                .select("id, name")
                .in_("id", top_concept_ids)
                .execute()
            )
            name_map = {c["id"]: c["name"] for c in (concepts.data or [])}
            for cid in top_concept_ids:
                if cid in name_map:
                    top_concepts.append({
                        "concept_id": cid,
                        "name": name_map[cid],
                        "seconds": concept_times[cid],
                    })

        return {
            "total_sessions": len(data),
            "total_reading_time": total_time,
            "avg_session_time": total_time // len(data) if data else 0,
            "top_concepts": top_concepts,
            "papers_read": papers_read,
        }
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Paper Sections ---

@router.get("/papers/{paper_id}/sections")
async def paper_sections(paper_id: str):
    """Get section map for a paper (for reading mode navigation)."""
    try:
        return await get_paper_sections(paper_id)
    except Exception as e:
        logger.error(f"Paper sections error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
