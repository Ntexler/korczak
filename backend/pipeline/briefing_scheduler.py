"""Briefing Scheduler — generates and stores personalized briefings.

Can run as a cron job or be triggered manually via API.

Usage:
  python -m backend.pipeline.briefing_scheduler --user demo-researcher-1 --type daily
  python -m backend.pipeline.briefing_scheduler --all --type weekly
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from backend.core.briefing_engine import generate_briefing
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def generate_and_store_briefing(
    user_id: str,
    briefing_type: str = "daily",
) -> dict | None:
    """Generate a briefing and store it in the database."""
    client = get_client()

    # Check if user has briefings enabled (skip for non-UUID mock users)
    locale = "en"
    import re
    is_uuid = bool(re.match(r'^[0-9a-f]{8}-', user_id))
    if is_uuid:
        try:
            prefs = client.table("briefing_preferences").select("*").eq(
                "user_id", user_id
            ).execute()
            if prefs.data and not prefs.data[0].get("enabled", True):
                logger.info(f"Briefings disabled for {user_id}")
                return None
            if prefs.data:
                locale = prefs.data[0].get("locale", "en")
        except Exception:
            pass

    # Generate briefing
    logger.info(f"Generating {briefing_type} briefing for {user_id}...")
    result = await generate_briefing(user_id=user_id, briefing_type=briefing_type)

    if result.get("status") != "generated":
        logger.warning(f"Briefing not generated: {result.get('status')}")
        return None

    # Store in DB
    briefing_data = {
        "user_id": user_id,
        "briefing_type": briefing_type,
        "content": result["content"],
        "raw_data": result.get("raw_data", {}),
        "tokens_used": result.get("tokens_used", 0),
    }

    db_result = client.table("briefings").insert(briefing_data).execute()

    if db_result.data:
        logger.info(
            f"  Stored briefing: {len(result['content'])} chars, "
            f"{result.get('tokens_used', 0)} tokens"
        )
        return db_result.data[0]

    return None


async def generate_for_all_users(briefing_type: str = "daily"):
    """Generate briefings for all users with briefings enabled."""
    client = get_client()

    # Get all users with briefings enabled (or default)
    # First check briefing_preferences
    prefs = client.table("briefing_preferences").select(
        "user_id"
    ).eq("enabled", True).execute()

    user_ids = set()
    if prefs.data:
        user_ids = {p["user_id"] for p in prefs.data}

    # Also include users from user_profiles who don't have preferences yet
    profiles = client.table("user_profiles").select("user_id").limit(100).execute()
    if profiles.data:
        for p in profiles.data:
            user_ids.add(p["user_id"])

    if not user_ids:
        # Fallback: generate for demo user
        user_ids = {"demo-researcher-1"}

    logger.info(f"Generating {briefing_type} briefings for {len(user_ids)} users")

    generated = 0
    for user_id in user_ids:
        result = await generate_and_store_briefing(user_id, briefing_type)
        if result:
            generated += 1

    logger.info(f"Generated {generated}/{len(user_ids)} briefings")
    return generated


async def get_latest_briefing(user_id: str) -> dict | None:
    """Get the most recent unread briefing for a user."""
    client = get_client()

    result = client.table("briefings").select("*").eq(
        "user_id", user_id
    ).is_("read_at", "null").order(
        "created_at", desc=True
    ).limit(1).execute()

    if result.data:
        return result.data[0]
    return None


async def mark_briefing_read(briefing_id: str):
    """Mark a briefing as read."""
    client = get_client()
    client.table("briefings").update({
        "read_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", briefing_id).execute()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate personalized briefings")
    parser.add_argument("--user", type=str, help="User ID to generate for")
    parser.add_argument("--all", action="store_true", help="Generate for all users")
    parser.add_argument("--type", type=str, default="daily",
                        choices=["daily", "weekly", "deep_dive"])
    args = parser.parse_args()

    if args.all:
        asyncio.run(generate_for_all_users(args.type))
    elif args.user:
        result = asyncio.run(generate_and_store_briefing(args.user, args.type))
        if result:
            print(f"\nBriefing generated:")
            print(result.get("content", ""))
        else:
            print("Failed to generate briefing")
    else:
        parser.error("Specify --user or --all")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
