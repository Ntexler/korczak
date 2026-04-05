"""Syllabus API — browse, fork, customize syllabi from MIT OCW, OpenStax, and custom."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Models ---

class ForkSyllabusRequest(BaseModel):
    user_id: str
    custom_title: Optional[str] = None


class UpdateUserSyllabusRequest(BaseModel):
    custom_title: Optional[str] = None
    custom_topics: Optional[dict] = None
    is_active: Optional[bool] = None


class CreateCustomSyllabusRequest(BaseModel):
    user_id: str
    title: str
    department: Optional[str] = None
    description: Optional[str] = None


class UpdateReadingProgressRequest(BaseModel):
    reading_id: str
    status: str  # "completed", "in_progress", "skipped"


# --- Template Syllabi ---

@router.get("/")
async def list_syllabi(
    department: Optional[str] = None,
    institution: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """List template syllabi (searchable by department, institution, keyword)."""
    try:
        client = get_client()
        query = (
            client.table("syllabi")
            .select("id, title, course_code, institution, department, instructor, year, url, paper_count, source")
            .eq("is_template", True)
        )
        if department:
            query = query.ilike("department", f"%{department}%")
        if institution:
            query = query.ilike("institution", f"%{institution}%")
        if source:
            query = query.eq("source", source)
        if search:
            query = query.or_(f"title.ilike.%{search}%,department.ilike.%{search}%,instructor.ilike.%{search}%")
        query = query.order("title").range(offset, offset + limit - 1)
        result = query.execute()
        return {"syllabi": result.data or [], "total": len(result.data or [])}
    except Exception as e:
        logger.error(f"List syllabi error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{syllabus_id}")
async def get_syllabus(syllabus_id: str):
    """Get syllabus with readings."""
    try:
        client = get_client()
        syl = client.table("syllabi").select("*").eq("id", syllabus_id).execute()
        if not syl.data:
            raise HTTPException(status_code=404, detail="Syllabus not found")

        readings = (
            client.table("syllabus_readings")
            .select("*, papers(id, title, authors, publication_year, cited_by_count)")
            .eq("syllabus_id", syllabus_id)
            .order("week")
            .order("position")
            .execute()
        )

        # Group readings by week
        weeks: dict[int, list] = {}
        for r in (readings.data or []):
            paper = r.pop("papers", None)
            week = r.get("week", 0)
            entry = {**r}
            if paper:
                entry["paper"] = paper
            weeks.setdefault(week, []).append(entry)

        return {
            **syl.data[0],
            "readings": readings.data or [],
            "readings_by_week": weeks,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get syllabus error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{syllabus_id}/concepts")
async def syllabus_concepts(syllabus_id: str):
    """Get concepts covered by a syllabus."""
    try:
        client = get_client()
        # Get papers from syllabus readings
        readings = (
            client.table("syllabus_readings")
            .select("paper_id")
            .eq("syllabus_id", syllabus_id)
            .not_.is_("paper_id", "null")
            .execute()
        )
        paper_ids = list({r["paper_id"] for r in (readings.data or [])})
        if not paper_ids:
            return {"concepts": []}

        # Get concepts from these papers
        pc = (
            client.table("paper_concepts")
            .select("concept_id, concepts(id, name, type, confidence)")
            .in_("paper_id", paper_ids)
            .execute()
        )

        seen = set()
        concepts = []
        for row in (pc.data or []):
            c = row.get("concepts")
            if c and c["id"] not in seen:
                seen.add(c["id"])
                concepts.append(c)

        return {"concepts": concepts, "total": len(concepts)}
    except Exception as e:
        logger.error(f"Syllabus concepts error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{syllabus_id}/graph")
async def syllabus_graph(syllabus_id: str, user_id: Optional[str] = None):
    """Get graph visualization data filtered to syllabus concepts."""
    try:
        client = get_client()
        result = client.rpc(
            "get_syllabus_graph",
            {"p_syllabus_id": syllabus_id, "p_user_id": user_id},
        ).execute()
        return {"nodes": result.data or []}
    except Exception as e:
        logger.error(f"Syllabus graph error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{syllabus_id}/progress")
async def syllabus_progress(syllabus_id: str, user_id: str = Query(...)):
    """Get 'Where Am I' progress data for a user's syllabus."""
    try:
        client = get_client()

        # Get user's custom syllabus if exists
        user_syl = (
            client.table("user_syllabi")
            .select("*")
            .eq("user_id", user_id)
            .eq("syllabus_id", syllabus_id)
            .limit(1)
            .execute()
        )
        progress = user_syl.data[0].get("progress", {}) if user_syl.data else {}

        # Get total readings
        readings = (
            client.table("syllabus_readings")
            .select("id, week, section, external_title")
            .eq("syllabus_id", syllabus_id)
            .order("week")
            .execute()
        )

        total = len(readings.data or [])
        completed = sum(1 for r in (readings.data or []) if progress.get(r["id"], {}).get("status") == "completed")

        return {
            "total_readings": total,
            "completed_readings": completed,
            "completion_pct": round(completed / total * 100, 1) if total > 0 else 0,
            "progress": progress,
            "readings": readings.data or [],
        }
    except Exception as e:
        logger.error(f"Syllabus progress error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- User Syllabi (Fork & Customize) ---

@router.post("/{syllabus_id}/fork")
async def fork_syllabus(syllabus_id: str, req: ForkSyllabusRequest):
    """Fork a template syllabus into user's custom syllabus."""
    try:
        client = get_client()

        # Get template
        template = client.table("syllabi").select("title").eq("id", syllabus_id).execute()
        if not template.data:
            raise HTTPException(status_code=404, detail="Syllabus not found")

        # Check if already forked
        existing = (
            client.table("user_syllabi")
            .select("id")
            .eq("user_id", req.user_id)
            .eq("syllabus_id", syllabus_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        result = client.table("user_syllabi").insert({
            "user_id": req.user_id,
            "syllabus_id": syllabus_id,
            "custom_title": req.custom_title or template.data[0]["title"],
            "is_active": True,
        }).execute()
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fork syllabus error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/list")
async def list_user_syllabi(user_id: str = Query(...)):
    """List user's custom syllabi."""
    try:
        client = get_client()
        result = (
            client.table("user_syllabi")
            .select("*, syllabi(title, department, institution, source)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"syllabi": result.data or []}
    except Exception as e:
        logger.error(f"List user syllabi error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/user/{user_syllabus_id}")
async def update_user_syllabus(user_syllabus_id: str, req: UpdateUserSyllabusRequest):
    """Update custom syllabus (add/remove readings, reorder, rename)."""
    try:
        client = get_client()
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = client.table("user_syllabi").update(data).eq("id", user_syllabus_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="User syllabus not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user syllabus error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/create")
async def create_custom_syllabus(req: CreateCustomSyllabusRequest):
    """Create a custom syllabus from scratch."""
    try:
        client = get_client()
        # Create the syllabus
        syl = client.table("syllabi").insert({
            "title": req.title,
            "department": req.department,
            "source": "custom",
            "is_template": False,
        }).execute()
        if not syl.data:
            raise HTTPException(status_code=500, detail="Failed to create syllabus")

        # Create user link
        user_syl = client.table("user_syllabi").insert({
            "user_id": req.user_id,
            "syllabus_id": syl.data[0]["id"],
            "custom_title": req.title,
            "is_active": True,
        }).execute()
        return user_syl.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create custom syllabus error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/{user_syllabus_id}/progress")
async def update_reading_progress(user_syllabus_id: str, req: UpdateReadingProgressRequest):
    """Update reading progress for a custom syllabus."""
    try:
        client = get_client()
        # Get current progress
        user_syl = (
            client.table("user_syllabi")
            .select("progress")
            .eq("id", user_syllabus_id)
            .execute()
        )
        if not user_syl.data:
            raise HTTPException(status_code=404, detail="User syllabus not found")

        progress = user_syl.data[0].get("progress", {})
        progress[req.reading_id] = {
            "status": req.status,
            "completed_at": "now()" if req.status == "completed" else None,
        }

        result = client.table("user_syllabi").update(
            {"progress": progress}
        ).eq("id", user_syllabus_id).execute()
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update progress error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
