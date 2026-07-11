"""Chappie's media missions — pre-fetch evidence clips for founding moments.

The "גם וגם" half: besides on-demand discovery, Chappie proactively brings
media for the concepts where it matters most — historical events and shaping
moments (type phenomenon/paradigm). Runs nightly; targeted, not a crawl.

Only concepts that plausibly HAVE founding footage get a pass, so we don't
burn interpretation cost on abstract theory that no clip illustrates.

Usage:
  python -m backend.agents.media_missions --limit 15
  python -m backend.agents.media_missions --concept <uuid>
"""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Event/moment-ish concepts are where founding footage lives.
_MOMENT_TYPES = ("phenomenon", "paradigm", "critique")


async def run_media_shift(limit: int = 15, per_concept: int = 3) -> dict:
    """Bring + interpret media for the most media-relevant concepts."""
    from backend.integrations.supabase_client import get_client
    from backend.integrations.media_sources import search_media
    from backend.agents.media_interpreter import assess_and_store

    client = get_client()
    # Prefer event/moment concepts that have no media yet.
    res = (client.table("concepts")
           .select("id,name,definition,type")
           .in_("type", list(_MOMENT_TYPES))
           .order("paper_count", desc=True).limit(limit * 3).execute())
    concepts = res.data or []

    covered = 0
    totals = {"concepts": 0, "stored": 0}
    for c in concepts:
        if covered >= limit:
            break
        # skip concepts that already have media
        existing = (client.table("media_evidence").select("id")
                    .eq("concept_id", c["id"]).limit(1).execute())
        if existing.data:
            continue

        claim = c.get("definition") or c["name"]
        records = await search_media(c["name"], limit_per_source=per_concept)
        if not records:
            continue
        stored_here = 0
        for rec in records[:per_concept]:
            row = await assess_and_store(
                client, rec, c["id"], c["name"], claim, brought_by="chappie")
            if row:
                stored_here += 1
        if stored_here:
            covered += 1
            totals["concepts"] += 1
            totals["stored"] += stored_here
            logger.info(f"Chappie brought {stored_here} clips for '{c['name']}'")

    return totals


async def run_for_concept(concept_id: str, per_concept: int = 4) -> dict:
    from backend.integrations.supabase_client import get_client
    from backend.integrations.media_sources import search_media
    from backend.agents.media_interpreter import assess_and_store

    client = get_client()
    res = client.table("concepts").select("id,name,definition").eq("id", concept_id).limit(1).execute()
    c = (res.data or [None])[0]
    if not c:
        return {"error": "concept not found"}
    claim = c.get("definition") or c["name"]
    records = await search_media(c["name"], limit_per_source=per_concept)
    stored = 0
    for rec in records[:per_concept]:
        if await assess_and_store(client, rec, c["id"], c["name"], claim, brought_by="chappie"):
            stored += 1
    return {"concept": c["name"], "stored": stored}


async def main():
    parser = argparse.ArgumentParser(description="Chappie media missions")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--per-concept", type=int, default=3)
    parser.add_argument("--concept", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.concept:
        print(await run_for_concept(args.concept, args.per_concept))
    else:
        print(await run_media_shift(args.limit, args.per_concept))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
