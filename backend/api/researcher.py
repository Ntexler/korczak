"""Researcher Profiles API — public identity, follows, activity feed."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateProfileRequest(BaseModel):
    user_id: str
    display_name: str
    bio: str | None = None
    institution: str | None = None
    role: str | None = None
    research_interests: list[str] = []
    website_url: str | None = None
    orcid: str | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    institution: str | None = None
    role: str | None = None
    research_interests: list[str] | None = None
    website_url: str | None = None
    orcid: str | None = None


# --- Profiles ---

@router.post("/profiles")
async def create_profile(request: CreateProfileRequest):
    """Create a public researcher profile."""
    try:
        client = get_client()
        data = request.model_dump(exclude_none=True)
        result = client.table("researcher_profiles").upsert(
            data, on_conflict="user_id"
        ).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        logger.error(f"Create profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str):
    """Get a researcher profile with stats."""
    try:
        client = get_client()
        profile = (
            client.table("researcher_profiles")
            .select("*")
            .eq("id", profile_id)
            .execute()
        )
        if not profile.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        p = profile.data[0]

        # Get counts
        summaries = client.table("concept_summaries").select("id", count="exact").eq("author_id", profile_id).execute()
        discussions = client.table("discussions").select("id", count="exact").eq("author_id", profile_id).execute()
        followers = client.table("researcher_follows").select("id", count="exact").eq("following_id", profile_id).execute()
        following = client.table("researcher_follows").select("id", count="exact").eq("follower_id", profile_id).execute()

        p["stats"] = {
            "summaries_written": summaries.count or 0,
            "discussions_started": discussions.count or 0,
            "followers": followers.count or 0,
            "following": following.count or 0,
        }
        return p
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/by-user/{user_id}")
async def get_profile_by_user(user_id: str):
    """Get researcher profile by user_id."""
    try:
        client = get_client()
        result = (
            client.table("researcher_profiles")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile by user error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, request: UpdateProfileRequest):
    """Update researcher profile."""
    try:
        client = get_client()
        data = request.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        data["updated_at"] = "now()"
        result = client.table("researcher_profiles").update(data).eq("id", profile_id).execute()
        return result.data[0] if result.data else {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Follows ---

@router.post("/profiles/{profile_id}/follow")
async def follow_researcher(
    profile_id: str,
    follower_id: str = Query(...),
):
    """Follow a researcher."""
    try:
        client = get_client()
        result = client.table("researcher_follows").upsert(
            {"follower_id": follower_id, "following_id": profile_id},
            on_conflict="follower_id,following_id",
        ).execute()

        # Log activity
        client.table("activity_feed").insert({
            "researcher_id": follower_id,
            "action_type": "followed_researcher",
            "target_type": "researcher",
            "target_id": profile_id,
        }).execute()

        return {"status": "following"}
    except Exception as e:
        logger.error(f"Follow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/profiles/{profile_id}/follow")
async def unfollow_researcher(
    profile_id: str,
    follower_id: str = Query(...),
):
    """Unfollow a researcher."""
    try:
        client = get_client()
        client.table("researcher_follows").delete().match(
            {"follower_id": follower_id, "following_id": profile_id}
        ).execute()
        return {"status": "unfollowed"}
    except Exception as e:
        logger.error(f"Unfollow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/{profile_id}/followers")
async def get_followers(profile_id: str, limit: int = Query(default=20, le=100)):
    """Get followers of a researcher."""
    try:
        client = get_client()
        result = (
            client.table("researcher_follows")
            .select("follower_id, researcher_profiles!researcher_follows_follower_id_fkey(id, display_name, institution, role)")
            .eq("following_id", profile_id)
            .limit(limit)
            .execute()
        )
        return {"followers": result.data or []}
    except Exception as e:
        # Fallback without join
        try:
            client = get_client()
            result = client.table("researcher_follows").select("follower_id").eq("following_id", profile_id).limit(limit).execute()
            return {"followers": result.data or []}
        except Exception as e2:
            logger.error(f"Get followers error: {e2}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e2))


# --- Activity Feed ---

@router.get("/feed")
async def activity_feed(
    researcher_id: str = Query(...),
    limit: int = Query(default=30, le=100),
):
    """Get activity feed for a researcher (their own + people they follow)."""
    try:
        client = get_client()

        # Get who this researcher follows
        follows = (
            client.table("researcher_follows")
            .select("following_id")
            .eq("follower_id", researcher_id)
            .execute()
        )
        following_ids = [f["following_id"] for f in (follows.data or [])]
        following_ids.append(researcher_id)  # Include own activity

        # Get recent activity from followed researchers
        result = (
            client.table("activity_feed")
            .select("*")
            .in_("researcher_id", following_ids)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return {"feed": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error(f"Activity feed error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_researchers(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, le=50),
):
    """Search researcher profiles by name or institution."""
    try:
        client = get_client()
        result = (
            client.table("researcher_profiles")
            .select("id, display_name, institution, role, research_interests, reputation_score")
            .or_(f"display_name.ilike.%{q}%,institution.ilike.%{q}%")
            .eq("is_public", True)
            .order("reputation_score", desc=True)
            .limit(limit)
            .execute()
        )
        return {"results": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error(f"Search researchers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
