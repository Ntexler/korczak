"""
Backfill `author_profiles` rows from existing papers (Feature 6.5, Stage B-2).

Walks the `papers.authors[]` JSONB across the corpus, ensures an
`author_profiles` row exists for each unique author (keyed on
openalex_id / orcid / normalized_name), enriches it from OpenAlex
(works_count, h_index, institution history, concepts), and generates
a short Claude-written bio.

Run iteratively — early runs create stubs and enrich the highest-cited
authors; later runs fill in the long tail.

Usage:
  python -m backend.pipeline.backfill_author_profiles --limit 200
  python -m backend.pipeline.backfill_author_profiles --limit 50 --skip-bios
  python -m backend.pipeline.backfill_author_profiles --enrich-only --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from backend.core.author_enricher import (
    ensure_author_profile,
    enrich_from_openalex,
    generate_bio,
)
from backend.integrations.supabase_client import get_client

load_dotenv()


def _iter_unique_authors(client, scan_limit: int):
    """Yield unique author dicts seen in `papers.authors`, ordered by paper citations.

    Uses a sliding window over `papers` since `authors` is a JSONB column;
    Supabase doesn't have efficient JSONB-array distinct via the REST API, so
    we deduplicate in Python.
    """
    seen: set[str] = set()
    offset = 0
    page_size = 200
    while offset < scan_limit:
        result = (
            client.table("papers")
            .select("authors")
            .order("cited_by_count", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return
        for row in rows:
            for a in (row.get("authors") or []):
                # Dedup key
                key = a.get("openalex_id") or a.get("orcid") or (a.get("name") or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                yield a
        offset += page_size


async def stub_authors(scan_limit: int, dry_run: bool) -> int:
    """Create author_profiles stubs for any author not yet represented.

    Returns count of stubs created (or that would be created in dry_run).
    """
    client = get_client()
    created = 0
    for a in _iter_unique_authors(client, scan_limit):
        if dry_run:
            created += 1
            continue
        existing = ensure_author_profile(
            openalex_id=a.get("openalex_id"),
            orcid=a.get("orcid"),
            name=a.get("name"),
            primary_institution=a.get("institution"),
        )
        if existing and existing.get("enriched_at") is None:
            # Counts only stubs we just created or that are still un-enriched.
            created += 1
    return created


async def enrich_pending(limit: int, dry_run: bool) -> int:
    """Enrich up to `limit` author_profiles rows that have not yet been enriched."""
    client = get_client()
    pending = (
        client.table("author_profiles")
        .select("*")
        .is_("enriched_at", "null")
        .limit(limit)
        .execute()
    )
    rows = pending.data or []
    print(f"  {len(rows)} profiles pending enrichment")

    enriched = 0
    for i, row in enumerate(rows):
        name = row.get("name") or row.get("openalex_id") or "?"
        print(f"  [{i+1}/{len(rows)}] enriching {name}")
        if dry_run:
            continue
        try:
            updated = await enrich_from_openalex(row)
            if updated:
                enriched += 1
        except Exception as e:
            print(f"    enrichment error: {e}")
        await asyncio.sleep(0.15)
    return enriched


async def generate_pending_bios(limit: int, dry_run: bool) -> int:
    """Generate bios for up to `limit` enriched profiles that still lack one."""
    client = get_client()
    pending = (
        client.table("author_profiles")
        .select("*")
        .not_.is_("enriched_at", "null")
        .is_("bio", "null")
        .limit(limit)
        .execute()
    )
    rows = pending.data or []
    print(f"  {len(rows)} profiles pending bio")

    generated = 0
    for i, row in enumerate(rows):
        name = row.get("name") or row.get("openalex_id") or "?"
        print(f"  [{i+1}/{len(rows)}] bio for {name}")
        if dry_run:
            continue
        try:
            updated = await generate_bio(row)
            if updated and updated.get("bio"):
                generated += 1
        except Exception as e:
            print(f"    bio error: {e}")
        await asyncio.sleep(0.05)
    return generated


async def run(limit: int, dry_run: bool, skip_bios: bool, enrich_only: bool, scan_limit: int) -> None:
    print(f"\n{'='*60}")
    print(f"AUTHOR PROFILES BACKFILL  limit={limit}, scan_limit={scan_limit}, dry_run={dry_run}")
    print(f"{'='*60}\n")

    if not enrich_only:
        print("Step 1: stubbing missing author_profiles rows from papers.authors[]")
        created = await stub_authors(scan_limit=scan_limit, dry_run=dry_run)
        print(f"  -> {created} new profile stubs\n")

    print("Step 2: enriching profiles from OpenAlex")
    enriched = await enrich_pending(limit=limit, dry_run=dry_run)
    print(f"  -> {enriched} profiles enriched\n")

    if not skip_bios:
        print("Step 3: generating bios via Claude")
        generated = await generate_pending_bios(limit=limit, dry_run=dry_run)
        print(f"  -> {generated} bios generated\n")

    print(f"{'='*60}\nDONE\n{'='*60}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Backfill author_profiles from existing papers")
    parser.add_argument("--limit", type=int, default=100, help="Per-step limit (enrichment + bios)")
    parser.add_argument("--scan-limit", type=int, default=2000, help="Papers to scan when stubbing authors")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-bios", action="store_true", help="Skip Claude bio generation step")
    parser.add_argument("--enrich-only", action="store_true", help="Skip stubbing — only enrich existing rows")
    args = parser.parse_args()

    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    asyncio.run(run(args.limit, args.dry_run, args.skip_bios, args.enrich_only, args.scan_limit))


if __name__ == "__main__":
    main()
