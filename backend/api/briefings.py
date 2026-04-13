"""Briefings API — personalized knowledge briefings."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.briefing_engine import generate_briefing, get_briefing_topics
from backend.pipeline.briefing_scheduler import (
    generate_and_store_briefing,
    get_latest_briefing,
    mark_briefing_read,
)
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


class BriefingPrefsRequest(BaseModel):
    user_id: str
    enabled: bool = True
    frequency: str = "weekly"  # daily | weekly | none
    preferred_time: str = "09:00"
    locale: str = "en"


@router.get("/latest/{user_id}")
async def latest_briefing(user_id: str):
    """Get the most recent unread briefing for a user."""
    try:
        briefing = await get_latest_briefing(user_id)
        if not briefing:
            # Generate one on the fly
            result = await generate_and_store_briefing(user_id, "daily")
            if result:
                return result
            raise HTTPException(status_code=404, detail="No briefing available")
        return briefing
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Briefing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def trigger_briefing(
    user_id: str,
    briefing_type: str = "daily",
):
    """Generate a new briefing on demand."""
    try:
        result = await generate_and_store_briefing(user_id, briefing_type)
        if result:
            return result
        raise HTTPException(status_code=500, detail="Briefing generation failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Briefing generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read/{briefing_id}")
async def read_briefing(briefing_id: str):
    """Mark a briefing as read."""
    try:
        await mark_briefing_read(briefing_id)
        return {"status": "read"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{user_id}")
async def briefing_history(user_id: str, limit: int = 10):
    """Get briefing history for a user."""
    client = get_client()
    result = client.table("briefings").select(
        "id, briefing_type, content, tokens_used, read_at, created_at"
    ).eq("user_id", user_id).order(
        "created_at", desc=True
    ).limit(limit).execute()
    return {"briefings": result.data, "total": len(result.data)}


@router.get("/topics/{user_id}")
async def topic_suggestions(user_id: str):
    """Get personalized topic suggestions."""
    try:
        topics = await get_briefing_topics(user_id)
        return {"topics": topics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences/{user_id}")
async def get_preferences(user_id: str):
    """Get briefing preferences for a user."""
    client = get_client()
    result = client.table("briefing_preferences").select("*").eq(
        "user_id", user_id
    ).execute()
    if result.data:
        return result.data[0]
    return {"user_id": user_id, "enabled": True, "frequency": "weekly",
            "preferred_time": "09:00", "locale": "en"}


@router.post("/preferences")
async def update_preferences(req: BriefingPrefsRequest):
    """Update briefing preferences."""
    client = get_client()
    try:
        result = client.table("briefing_preferences").upsert({
            "user_id": req.user_id,
            "enabled": req.enabled,
            "frequency": req.frequency,
            "preferred_time": req.preferred_time,
            "locale": req.locale,
        }, on_conflict="user_id").execute()
        return result.data[0] if result.data else {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
