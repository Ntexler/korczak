"""Courses API — serves generated courses and collects feedback.

Includes abuse protection on the feedback mechanism.
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client
from backend.pipeline.syllabus_models import (
    MAX_VOTES_PER_USER_PER_DAY,
    MAX_VOTES_PER_USER_PER_COURSE,
    ANOMALY_DOWNVOTE_THRESHOLD,
    ANOMALY_DOWNVOTE_RATIO,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request models ---

class FeedbackRequest(BaseModel):
    user_id: str
    course_reading_id: str
    vote_type: str  # upvote | downvote


# --- Endpoints ---

@router.get("/generated")
async def list_generated_courses(
    department: str | None = None,
    level: str | None = None,
    limit: int = 50,
):
    """List generated courses, optionally filtered."""
    client = get_client()
    query = client.table("generated_courses").select(
        "id, department, level, title, description, "
        "source_syllabi_count, reading_count, ai_recommendations_count, "
        "generated_at, is_published"
    ).eq("is_published", True)

    if department:
        query = query.eq("department", department)
    if level:
        query = query.eq("level", level)

    result = query.order("department").limit(limit).execute()
    return {"courses": result.data, "total": len(result.data)}


@router.get("/generated/{course_id}")
async def get_generated_course(course_id: str):
    """Get a full generated course with weekly breakdown."""
    client = get_client()

    course = client.table("generated_courses").select("*").eq("id", course_id).execute()
    if not course.data:
        raise HTTPException(status_code=404, detail="Course not found")

    readings = client.table("course_readings").select("*").eq(
        "course_id", course_id
    ).order("week").order("position").execute()

    # Group readings by week
    weeks = {}
    for r in readings.data or []:
        week = r["week"]
        if week not in weeks:
            weeks[week] = {"required": [], "recommended": [], "supplementary": []}
        weeks[week][r.get("section", "required")].append(r)

    course_data = course.data[0]
    course_data["readings"] = readings.data
    course_data["readings_by_week"] = weeks
    return course_data


@router.get("/analysis/{department}")
async def get_department_analysis(department: str):
    """Get department analysis — reading scores, tier distribution, gaps."""
    client = get_client()

    scores = client.table("reading_scores").select("*").eq(
        "department", department
    ).order("combined_score", desc=True).execute()

    if not scores.data:
        raise HTTPException(status_code=404, detail=f"No data for department: {department}")

    # Tier counts
    tiers = {}
    for s in scores.data:
        tier = s.get("tier", "niche")
        tiers[tier] = tiers.get(tier, 0) + 1

    # Institution stats
    all_institutions = set()
    for s in scores.data:
        for inst in (s.get("source_institutions") or []):
            all_institutions.add(inst)

    return {
        "department": department,
        "total_readings": len(scores.data),
        "tier_distribution": tiers,
        "institutions": sorted(all_institutions),
        "top_20": scores.data[:20],
        "ai_recommended": [s for s in scores.data if s["tier"] == "ai_recommended"],
    }


@router.get("/scores")
async def get_reading_scores(
    department: str | None = None,
    tier: str | None = None,
    min_score: float = 0.0,
    limit: int = 100,
):
    """Get reading scores with filters."""
    client = get_client()
    query = client.table("reading_scores").select("*")

    if department:
        query = query.eq("department", department)
    if tier:
        query = query.eq("tier", tier)
    if min_score > 0:
        query = query.gte("combined_score", min_score)

    result = query.order("combined_score", desc=True).limit(limit).execute()
    return {"scores": result.data, "total": len(result.data)}


@router.get("/compare")
async def compare_syllabi(department: str):
    """Compare institution syllabi side-by-side for a department."""
    client = get_client()

    syllabi = client.table("syllabi").select(
        "id, title, institution, source"
    ).eq("department", department).execute()

    if not syllabi.data:
        raise HTTPException(status_code=404, detail=f"No syllabi for: {department}")

    # Group by institution
    by_institution = {}
    for s in syllabi.data:
        inst = s.get("institution", "Unknown")
        if inst not in by_institution:
            by_institution[inst] = []
        by_institution[inst].append(s)

    # Get top readings per institution
    comparison = {}
    for inst, inst_syllabi in by_institution.items():
        syl_ids = [s["id"] for s in inst_syllabi]
        readings = client.table("syllabus_readings").select(
            "external_title, week, section"
        ).in_("syllabus_id", syl_ids).limit(50).execute()
        comparison[inst] = {
            "syllabi_count": len(inst_syllabi),
            "top_readings": [r["external_title"] for r in (readings.data or []) if r.get("external_title")][:20],
        }

    return {"department": department, "institutions": comparison}


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Submit a vote on a course reading. Includes abuse protection."""
    client = get_client()

    if req.vote_type not in ("upvote", "downvote"):
        raise HTTPException(status_code=400, detail="vote_type must be 'upvote' or 'downvote'")

    # --- Abuse Protection ---

    # 1. Check daily vote limit
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    daily_votes = client.table("reading_feedback").select(
        "id", count="exact"
    ).eq("user_id", req.user_id).gte("created_at", day_ago).execute()

    if (daily_votes.count or 0) >= MAX_VOTES_PER_USER_PER_DAY:
        raise HTTPException(status_code=429, detail="Daily vote limit reached (10/day)")

    # 2. Check per-course vote limit
    reading = client.table("course_readings").select(
        "course_id"
    ).eq("id", req.course_reading_id).execute()

    if not reading.data:
        raise HTTPException(status_code=404, detail="Reading not found")

    course_id = reading.data[0]["course_id"]
    course_readings = client.table("course_readings").select("id").eq(
        "course_id", course_id
    ).execute()
    course_reading_ids = [r["id"] for r in course_readings.data] if course_readings.data else []

    user_course_votes = client.table("reading_feedback").select(
        "id", count="exact"
    ).eq("user_id", req.user_id).in_("course_reading_id", course_reading_ids).execute()

    if (user_course_votes.count or 0) >= MAX_VOTES_PER_USER_PER_COURSE:
        raise HTTPException(status_code=429, detail="Per-course vote limit reached (3/course)")

    # 3. Determine vote weight based on user reputation
    vote_weight = await _get_user_vote_weight(client, req.user_id)

    # 4. Check for anomaly: user downvoting >80% of readings in a course
    is_suspicious = False
    if req.vote_type == "downvote" and user_course_votes.count and course_reading_ids:
        downvotes = client.table("reading_feedback").select(
            "id", count="exact"
        ).eq("user_id", req.user_id).eq(
            "vote_type", "downvote"
        ).in_("course_reading_id", course_reading_ids).execute()

        total_votes = (user_course_votes.count or 0) + 1
        downvote_ratio = ((downvotes.count or 0) + 1) / total_votes
        if downvote_ratio > ANOMALY_DOWNVOTE_RATIO and total_votes >= 3:
            is_suspicious = True
            vote_weight = 0.0
            logger.warning(f"Suspicious voting pattern: user {req.user_id} on course {course_id}")

    # 5. Check for anomaly: reading getting mass downvoted
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent_downvotes = client.table("reading_feedback").select(
        "id", count="exact"
    ).eq("course_reading_id", req.course_reading_id).eq(
        "vote_type", "downvote"
    ).gte("created_at", hour_ago).execute()

    if (recent_downvotes.count or 0) >= ANOMALY_DOWNVOTE_THRESHOLD:
        is_suspicious = True
        vote_weight = 0.0
        logger.warning(f"Mass downvote detected on reading {req.course_reading_id}")

    # --- Insert vote ---
    try:
        result = client.table("reading_feedback").upsert({
            "user_id": req.user_id,
            "course_reading_id": req.course_reading_id,
            "vote_type": req.vote_type,
            "vote_weight": vote_weight,
            "is_suspicious": is_suspicious,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,course_reading_id").execute()

        return {
            "status": "recorded",
            "vote_weight": vote_weight,
            "is_suspicious": is_suspicious,
        }
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail="Failed to record vote")


async def _get_user_vote_weight(client, user_id: str) -> float:
    """Determine vote weight based on user reputation.

    - New users (<5 interactions): 0.3x
    - Active users (5-50): 1.0x
    - Power users (50+, no flags): 1.5x
    - Flagged users (2+ flags): 0.0x
    """
    # Check for flags
    flags = client.table("reading_feedback").select(
        "id", count="exact"
    ).eq("user_id", user_id).eq("is_suspicious", True).execute()

    if (flags.count or 0) >= 2:
        return 0.0

    # Check interaction count
    profile = client.table("user_profiles").select(
        "session_count"
    ).eq("user_id", user_id).execute()

    if not profile.data:
        return 0.3  # New user

    sessions = profile.data[0].get("session_count", 0)
    if sessions >= 50:
        return 1.5
    elif sessions >= 5:
        return 1.0
    return 0.3
